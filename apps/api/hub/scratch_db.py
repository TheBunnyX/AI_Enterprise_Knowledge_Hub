"""Throw-away PostgreSQL databases for tests and the evaluation, on the same server Docker Compose runs.

Start it with `docker compose -f compose.yaml -f compose.dev.yaml up -d postgres`. That override publishes the port on 127.0.0.1 only.
Set TEST_DATABASE_URL (an owner-role URL of any database on the server) to use a different server.
"""
import os, uuid
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


def server_url():
    explicit = os.getenv('TEST_DATABASE_URL')
    if explicit: return make_url(explicit)
    env = ROOT / '.env'
    password = ''
    if env.exists():
        for line in env.read_text(encoding='utf-8').splitlines():
            if line.startswith('POSTGRES_PASSWORD='): password = line.split('=', 1)[1].strip()
    if not password: raise RuntimeError('No PostgreSQL to test against: run scripts/setup-env.ps1, or set TEST_DATABASE_URL.')
    return make_url(f'postgresql+psycopg://hub:{password}@127.0.0.1:5432/postgres')


def create(prefix='hub_scratch'):
    """Create an empty database and return (url, drop). `drop` removes it again."""
    base = server_url(); name = f'{prefix}_{uuid.uuid4().hex[:10]}'
    admin = create_engine(base.set(database='postgres'), isolation_level='AUTOCOMMIT')
    try:
        with admin.connect() as c: c.execute(text(f'create database "{name}"'))
    except Exception as e:
        raise RuntimeError(f'Cannot reach PostgreSQL at {base.host}:{base.port}. Start it with: docker compose -f compose.yaml -f compose.dev.yaml up -d postgres ({e.__class__.__name__})') from e

    def drop():
        with admin.connect() as c:
            c.execute(text(f'drop database if exists "{name}" with (force)'))
        admin.dispose()
    return base.set(database=name).render_as_string(hide_password=False), drop
