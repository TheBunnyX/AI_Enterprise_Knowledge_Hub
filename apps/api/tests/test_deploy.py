"""Things that only show up when the system is installed somewhere new: migrations on an empty database, production settings."""
import os, subprocess, sys
from pathlib import Path
from sqlalchemy import create_engine, inspect

API = Path(__file__).resolve().parents[1]


def test_migrations_build_the_current_schema_on_an_empty_database(tmp_path):
    import hub.main  # noqa: F401 - every model module is imported by the app
    from hub.database import Base
    from hub.scratch_db import create
    url, drop = create('hub_fresh')
    try:
        env = {**os.environ, 'DATA_DIR': str(tmp_path), 'DATABASE_URL': url}; env.pop('MIGRATION_DATABASE_URL', None)
        done = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=API, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
        assert done.returncode == 0, done.stderr[-1500:]
        engine = create_engine(url); found = inspect(engine)
        missing = _missing(Base, found)
        engine.dispose()
    finally:
        drop()
    assert missing == []  # a model column no migration creates would only fail in production, where tables are not auto-created


def _missing(Base, found):
    return [f'{t.name}.{c.name}' for t in Base.metadata.sorted_tables for c in t.columns
            if t.name not in found.get_table_names() or c.name not in {x['name'] for x in found.get_columns(t.name)}]


def test_demo_accounts_are_offered_outside_production(client, monkeypatch):
    monkeypatch.setenv('DEMO_ACCOUNTS', 'ผู้ใช้งาน|member@local.test|secret-password')
    assert client.get('/api/config').json()['demo_accounts'] == [{'label': 'ผู้ใช้งาน', 'email': 'member@local.test', 'password': 'secret-password'}]


def test_demo_account_passwords_are_never_served_in_production(client, monkeypatch):
    monkeypatch.setenv('DEMO_ACCOUNTS', 'ผู้ดูแลระบบ|admin@local.test|secret-password')
    monkeypatch.setenv('APP_ENV', 'production')
    body = client.get('/api/config')
    assert body.json()['demo_accounts'] == [] and 'secret-password' not in body.text
