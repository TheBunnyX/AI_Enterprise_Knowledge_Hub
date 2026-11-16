import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA = Path(os.getenv('DATA_DIR', 'data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
URL = os.getenv('DATABASE_URL', '')
if not URL.startswith('postgresql'):
    raise RuntimeError('DATABASE_URL must be a PostgreSQL URL (the Compose database). Start it with `docker compose up -d postgres`; see README.md.')
engine = create_engine(URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)

# Schema owner (migrations, backups, RLS setup). The app itself connects as an unprivileged role so PostgreSQL row-level security applies.
OWNER_URL = os.getenv('MIGRATION_DATABASE_URL') or URL
def owner_engine():
    return create_engine(OWNER_URL, pool_pre_ping=True)

_SCOPE = "select set_config('app.tenant_id', %s, true), set_config('app.bypass', %s, true)"

@event.listens_for(SessionLocal, 'after_begin')
def _apply_scope(session, transaction, connection):
    """Every transaction is tenant-scoped when the session has a tenant, otherwise it is a trusted system context (login, workers, super admin)."""
    tenant = session.info.get('tenant')
    connection.exec_driver_sql(_SCOPE, (tenant or '', 'off' if tenant else 'on'))

def scope_to_tenant(db, tenant):
    """Restrict this session to one tenant at the database level (PostgreSQL RLS), including the transaction already open."""
    db.info['tenant'] = tenant
    db.connection().exec_driver_sql(_SCOPE, (tenant, 'off'))

class Base(DeclarativeBase):
    pass

def db_session():
    with SessionLocal() as db:
        yield db
