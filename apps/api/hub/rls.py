"""PostgreSQL row-level security for tenant data. Idempotent: run after every migration and after a database restore.

The app connects as an unprivileged role (DATABASE_URL); the schema owner (MIGRATION_DATABASE_URL) owns the tables and bypasses
the policies. A table is protected when it has a tenant_id column. A transaction sees only its tenant's rows when the session
set app.tenant_id (see database.scope_to_tenant); trusted system contexts set app.bypass instead."""
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from .database import OWNER_URL, URL

log = logging.getLogger(__name__)
POLICY = "tenant_id::text = current_setting('app.tenant_id', true) OR current_setting('app.bypass', true) = 'on'"

def tenant_tables(conn):
    return [r[0] for r in conn.execute(text(
        "select c.table_name from information_schema.columns c join information_schema.tables t "
        "on t.table_schema = c.table_schema and t.table_name = c.table_name "
        "where c.table_schema = 'public' and c.column_name = 'tenant_id' and t.table_type = 'BASE TABLE' order by 1"))]

def quote(conn, name):
    return conn.scalar(text('select quote_ident(:n)'), {'n': name})

def apply(conn, app_user, app_password):
    """Create the app role if needed, grant data access and enable a tenant policy on every tenant table. Returns protected tables."""
    user = quote(conn, app_user)
    literal = conn.scalar(text('select quote_literal(:p)'), {'p': app_password})
    verb = 'ALTER' if conn.scalar(text('select 1 from pg_roles where rolname = :r'), {'r': app_user}) else 'CREATE'
    conn.exec_driver_sql(f'{verb} ROLE {user} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {literal}'.replace('%', '%%'))
    conn.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO {user}')
    conn.exec_driver_sql(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {user}')
    conn.exec_driver_sql(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {user}')
    tables = tenant_tables(conn)
    for table in tables:
        t = quote(conn, table)
        conn.exec_driver_sql(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY')
        conn.exec_driver_sql(f'DROP POLICY IF EXISTS tenant_isolation ON {t}')
        conn.exec_driver_sql(f'CREATE POLICY tenant_isolation ON {t} USING ({POLICY})')
    return tables

def apply_url(owner_url):
    app = make_url(URL)
    engine = create_engine(owner_url)
    try:
        if make_url(owner_url).username == app.username: return []  # single-role setup: nothing to enforce
        with engine.begin() as conn: return apply(conn, app.username, app.password or '')
    finally:
        engine.dispose()

if __name__ == '__main__':
    if not URL.startswith('postgresql'): print('RLS skipped: not PostgreSQL')
    else:
        done = apply_url(OWNER_URL)
        print(f'RLS enabled on {len(done)} tables' if done else 'RLS skipped: DATABASE_URL and MIGRATION_DATABASE_URL use the same role')
