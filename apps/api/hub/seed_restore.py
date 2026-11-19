"""First-start data seed: restore an encrypted .akh snapshot so a fresh deploy (e.g. Dokploy) starts with the same data.
Runs only when SEED_BACKUP_URL is set, no marker exists and the database has no users. Never overwrites existing data."""
import os,sys
from pathlib import Path
import httpx
from sqlalchemy import text

def marker():return Path(os.getenv('DATA_DIR','/data'))/'.seed-restored'

def empty(engine):
    with engine.connect() as c:return c.execute(text('SELECT count(*) FROM users')).scalar()==0

def download(url,token,target):
    headers={'Accept':'application/octet-stream',**({'Authorization':'Bearer '+token} if token else {})}
    with httpx.stream('GET',url,headers=headers,follow_redirects=True,timeout=httpx.Timeout(60,read=600)) as r:
        r.raise_for_status()
        with open(target,'wb') as f:
            for chunk in r.iter_bytes(1024*1024):f.write(chunk)

def run():
    url=os.getenv('SEED_BACKUP_URL','').strip()
    if not url or marker().exists():return 'skipped'
    from .database import owner_engine,OWNER_URL
    engine=owner_engine()
    if not empty(engine):
        marker().write_text('existing data');return 'existing'
    from . import backups
    backups.ROOT.mkdir(parents=True,exist_ok=True)
    tmp=backups.ROOT/'seed-download.akh'
    try:
        download(url,os.getenv('SEED_BACKUP_TOKEN','').strip(),tmp)
        backups.restore_archive(tmp,OWNER_URL,live=True)
    finally:
        tmp.unlink(missing_ok=True)
    engine.dispose()
    ids=backups.reset_restored_state()
    try:
        from .jobs import schedule_ingest
        for i in ids:schedule_ingest(i,retry=True)
    except Exception as e:print('seed: reindex scheduling failed:',type(e).__name__,file=sys.stderr)
    marker().write_text('restored');return 'restored:%d documents'%len(ids)

if __name__=='__main__':print('seed:',run())
