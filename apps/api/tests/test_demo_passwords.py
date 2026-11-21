import os
from sqlalchemy import select
from hub.auth import passwords
from hub.database import SessionLocal
from hub.models import User
from hub.seed import sync_demo_passwords


def test_demo_passwords_follow_the_setting(client, monkeypatch):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.role == 'SUPER_ADMIN'))
        email, old = user.email, user.password_hash
        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.setenv('DEMO_ACCOUNTS', f'Admin|{email}|first-pass-1;Other|nobody@local.test|x')
        assert sync_demo_passwords(db) == 1 and passwords.verify('first-pass-1', user.password_hash)
        assert sync_demo_passwords(db) == 0  # already matching: nothing rewritten
        monkeypatch.setenv('APP_ENV', 'production')
        monkeypatch.setenv('DEMO_ACCOUNTS', f'Admin|{email}|second-pass-2')
        assert sync_demo_passwords(db) == 0
        user.password_hash = old; db.commit()
