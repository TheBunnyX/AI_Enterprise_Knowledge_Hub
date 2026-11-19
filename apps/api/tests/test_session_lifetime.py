"""A sign-in lasts one day, counted from signing in; SESSION_HOURS can change that within sane limits."""
import time
import pytest
from sqlalchemy import select, delete
from conftest import login_as
from hub import auth
from hub.database import SessionLocal
from hub.models import LoginSession, User


def newest_session(email):
    with SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.email == email))
        return db.scalars(select(LoginSession).where(LoginSession.user_id == uid).order_by(LoginSession.expires.desc())).first()


def test_a_session_and_its_cookie_last_one_day(client, monkeypatch):
    monkeypatch.delenv('SESSION_HOURS', raising=False)
    before = time.time()
    r = login_as(client, 'member')
    assert r.status_code == 200
    assert 'Max-Age=86400' in r.headers['set-cookie'] and 'HttpOnly' in r.headers['set-cookie']
    s = newest_session('member@local.test')
    assert before + 86400 - 5 <= s.expires <= time.time() + 86400 + 5


def test_the_session_ends_after_a_day_and_not_before(client, monkeypatch):
    monkeypatch.delenv('SESSION_HOURS', raising=False)
    login_as(client, 'member')
    assert client.get('/api/auth/me').status_code == 200
    with SessionLocal() as db:  # 23 hours in: still valid; 25 hours in: gone
        s = db.scalars(select(LoginSession)).first(); signed_in = s.expires - 86400
        s.expires = signed_in + 86400 - 3600 * 1; db.commit()
    assert client.get('/api/auth/me').status_code == 200
    with SessionLocal() as db:
        s = db.scalars(select(LoginSession)).first(); s.expires = time.time() - 1; db.commit()
    assert client.get('/api/auth/me').status_code == 401


@pytest.mark.parametrize('value, seconds', [('2', 7200), ('0.5', 1800), ('0', 900), ('-3', 900), ('9999', 30 * 86400), ('abc', 86400), ('', 86400)])
def test_session_hours_is_configurable_but_bounded(monkeypatch, value, seconds):
    monkeypatch.setenv('SESSION_HOURS', value)
    assert auth.session_seconds() == seconds


def test_the_configured_lifetime_reaches_the_cookie(client, monkeypatch):
    monkeypatch.setenv('SESSION_HOURS', '2')
    r = login_as(client, 'member')
    assert 'Max-Age=7200' in r.headers['set-cookie']
