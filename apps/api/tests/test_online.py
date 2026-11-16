import time
from sqlalchemy import select, update
from hub.database import SessionLocal
from hub.models import User


def test_online_dot_follows_recent_activity(admin):
    me = next(u for u in admin.get('/api/admin/users').json() if u['role'] == 'SUPER_ADMIN')
    assert me['online'] is True  # this very session just made authenticated requests
    others = [u for u in admin.get('/api/admin/users').json() if u['id'] != me['id']]
    assert others and not any(u['online'] for u in others)  # nobody else has used the system

    with SessionLocal() as db:  # simulate the admin going idle for 10 minutes
        db.execute(update(User).where(User.id == me['id']).values(last_seen=time.time() - 600)); db.commit()
    # the next request refreshes last_seen, so check the stored value through a fresh read
    with SessionLocal() as db:
        assert time.time() - db.scalar(select(User.last_seen).where(User.id == me['id'])) > 120
    assert admin.get('/api/admin/users').json()  # request re-marks the user active
    assert next(u for u in admin.get('/api/admin/users').json() if u['id'] == me['id'])['online'] is True
