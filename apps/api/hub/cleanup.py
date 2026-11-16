"""Housekeeping for data that has outlived its purpose and would otherwise grow forever (and be copied into every backup).

- sign-in sessions past their expiry
- chat attachments: temporary files for one question, kept CHAT_ATTACHMENT_HOURS (default 24) after upload
- files the agent generated, once their download window (generated.RETENTION_DAYS) has ended
- agent runs that waited for their user longer than agent_store.PAUSE_HOURS

Runs once when the API starts and hourly from the scheduler. Safe to run at any time and from several processes.
"""
import os, time
from sqlalchemy import select, delete
from .database import SessionLocal
from .models import LoginSession, Organization, now
from . import storage


def run():
    """Delete what has expired; returns how many of each kind were removed."""
    from .generated import GeneratedFile
    from .agent_store import purge_expired
    done = {'sessions': 0, 'attachments': 0, 'generated_files': 0, 'agent_runs': 0}
    with SessionLocal() as db:  # system context: housekeeping covers every tenant
        done['sessions'] = db.execute(delete(LoginSession).where(LoginSession.expires < time.time())).rowcount
        for f in db.scalars(select(GeneratedFile).where(GeneratedFile.expires_at < now())):
            try: storage.remove(f.storage_key)
            except Exception: continue  # storage unavailable: keep the row so the next run tries again
            db.delete(f); done['generated_files'] += 1
        db.commit()
        tenants = list(db.scalars(select(Organization.id)))
    cutoff = time.time() - float(os.getenv('CHAT_ATTACHMENT_HOURS', '24')) * 3600
    for tenant in tenants:
        for key, modified in list(storage.entries(f'{tenant}/chat-attachments/')):
            if modified >= cutoff: continue
            try: storage.remove(key); done['attachments'] += 1
            except Exception: pass
    done['agent_runs'] = purge_expired()  # agent runs nobody answered
    return done
