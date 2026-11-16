"""Real ClamAV + encrypted backup rehearsal. Never restore the live database."""
import hashlib,os,json,time
from uuid import uuid4
from sqlalchemy import create_engine,text,select,func
from fastapi import HTTPException
from .database import OWNER_URL as URL,SessionLocal
from .models import Document
from .ops_models import Backup
from . import backups,storage,antivirus

def main():
    antivirus.ping()
    assert antivirus.scan(b'Harmless integration check')=='clean'
    # Standard non-malicious antivirus test signature, held only in memory.
    signature=b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
    try:antivirus.scan(signature)
    except HTTPException as exc:assert exc.status_code==422
    else:raise AssertionError('EICAR was not rejected')
    with SessionLocal() as db:
        row=Backup();db.add(row);db.commit();id=row.id
        count=db.scalar(select(func.count()).select_from(Document))
    backups.create_snapshot(id)
    manifest=backups.read_manifest(id)
    suffix=uuid4().hex
    database='hub_restore_check_'+suffix
    prefix='restore-rehearsal/'+suffix
    admin=create_engine(backups.make_url(URL).set(database='postgres'),isolation_level='AUTOCOMMIT')
    target=backups.make_url(URL).set(database=database)
    with admin.connect() as c:c.execute(text('CREATE DATABASE '+database))
    restored=None
    try:
        backups.restore_snapshot(id,target.render_as_string(hide_password=False),target_prefix=prefix)
        restored=create_engine(target)
        with restored.connect() as c:
            assert c.scalar(text('SELECT count(*) FROM documents'))==count
            assert c.scalar(text("SELECT count(*) FROM alembic_version"))==1
        for item in manifest['files']:
            raw=storage.get(prefix+'/'+item['key'])
            assert hashlib.sha256(raw).hexdigest()==item['sha256']
        print(json.dumps({'antivirus':'real ClamAV clean + EICAR rejected','backup_id':id,'database':'isolated PostgreSQL restore verified','documents':count,'files_verified':len(manifest['files']),'live_restore_performed':False}))
    finally:
        if restored:restored.dispose()
        with admin.connect() as c:c.execute(text('DROP DATABASE '+database+' WITH (FORCE)'))
        admin.dispose()
        for item in manifest['files']:storage.remove(prefix+'/'+item['key'])

if __name__=='__main__':main()
