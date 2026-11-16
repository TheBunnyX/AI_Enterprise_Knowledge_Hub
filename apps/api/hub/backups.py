"""Encrypted PostgreSQL + immutable file snapshots. Restore rehearsal uses isolated targets."""
import hashlib,json,os,secrets,shutil,subprocess,tempfile,time,zipfile,threading
from pathlib import Path
from datetime import datetime,timezone
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from sqlalchemy import select,func,delete
from sqlalchemy.engine import make_url
from .database import DATA,URL,OWNER_URL,SessionLocal,engine
from .models import now,Document
from .ops_models import Backup,TaskRun
from .feature_models import Setting
from . import storage,alerts

ROOT=Path(os.getenv('BACKUP_DIR',str(DATA/'backups'))).resolve()
MAGIC=b'AKHBK01'
def secret():
    raw=os.getenv('BACKUP_ENCRYPTION_KEY') or os.getenv('SECRETS_KEY')
    if not raw:raise RuntimeError('Backup encryption key is not configured')
    return hashlib.sha256(('ai-knowledge-hub-backup-v1:'+raw).encode()).digest()

def encrypt(source,target):
    nonce=secrets.token_bytes(12);c=Cipher(algorithms.AES(secret()),modes.GCM(nonce)).encryptor()
    with open(source,'rb') as inp,open(target,'wb') as out:
        out.write(MAGIC+nonce)
        for chunk in iter(lambda:inp.read(1024*1024),b''):out.write(c.update(chunk))
        out.write(c.finalize());out.write(c.tag)

def decrypt(source,target):
    with open(source,'rb') as inp,open(target,'wb') as out:
        if inp.read(len(MAGIC))!=MAGIC:raise ValueError('Invalid backup format')
        nonce=inp.read(12);inp.seek(-16,2);tag=inp.read(16);end=inp.tell()-16
        inp.seek(len(MAGIC)+12);c=Cipher(algorithms.AES(secret()),modes.GCM(nonce,tag)).decryptor()
        while inp.tell()<end:out.write(c.update(inp.read(min(1024*1024,end-inp.tell()))))
        out.write(c.finalize())

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def pg_args(url):
    u=make_url(url)
    if not u.drivername.startswith('postgresql'):raise RuntimeError('Backups require the PostgreSQL Docker stack')
    return ['-h',u.host or 'localhost','-p',str(u.port or 5432),'-U',u.username or 'hub','-d',u.database],{**os.environ,'PGPASSWORD':u.password or ''}

def keys():
    if os.getenv('S3_ENDPOINT'):
        client=storage.s3()
        for page in client.get_paginator('list_objects_v2').paginate(Bucket=os.getenv('S3_BUCKET','knowledge')):
            for item in page.get('Contents',[]):yield item['Key']
    else:
        root=DATA/'files'
        if root.exists():
            for path in root.rglob('*'):
                if path.is_file():yield path.relative_to(root).as_posix()

def sync_catalog():
    ROOT.mkdir(parents=True,exist_ok=True)
    with SessionLocal() as db:
        for path in ROOT.glob('*.json'):
            try:
                item=json.loads(path.read_text());id=item['id']
                if path.stem!=id or not (ROOT/(id+'.akh')).is_file():continue
                row=db.get(Backup,id)
                if not row:row=Backup(id=id);db.add(row)
                for key in ('filename','size','file_count','sha256','completed_at','automatic'):setattr(row,key,item[key])
                row.status='completed';row.error=''
            except (KeyError,ValueError,OSError):continue
        db.commit()

def create_snapshot(id,preserve=()):
    ROOT.mkdir(parents=True,exist_ok=True)
    with SessionLocal() as db:
        row=db.get(Backup,id)
        if not row or row.status not in ('queued','failed'):return
        row.status='processing';db.commit();automatic=row.automatic
    try:
        secret()
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            tmp=Path(tmp);dump=tmp/'database.dump';args,env=pg_args(OWNER_URL)
            subprocess.run(['pg_dump',*args,'-Fc','--no-owner','-f',str(dump)],env=env,capture_output=True,timeout=600,check=True)
            manifest={'format':1,'created_at':now(),'database':'database.dump','files':[],'keys_required':['SECRETS_KEY / BACKUP_ENCRYPTION_KEY'],'database_sha256':digest(dump)}
            archive=tmp/'snapshot.zip'
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
                z.write(dump,'database.dump')
                for index,key in enumerate(keys()):
                    data=storage.get(key);entry=f'files/{index:08d}.bin';z.writestr(entry,data)
                    manifest['files'].append({'key':key,'entry':entry,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
                z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
            target=ROOT/(id+'.akh');encrypt(archive,tmp/'encrypted');os.replace(tmp/'encrypted',target)
            item={'id':id,'filename':id+'.akh','size':target.stat().st_size,'file_count':len(manifest['files']),'sha256':digest(target),'completed_at':now(),'automatic':automatic}
            temp_meta=ROOT/(id+'.tmp');temp_meta.write_text(json.dumps(item));os.replace(temp_meta,ROOT/(id+'.json'))
        sync_catalog();alerts.resolve('backup-failed');replicate_offsite(id)
        retain=int(os.getenv('BACKUP_RETENTION','7'))
        with SessionLocal() as db:
            older=db.scalars(select(Backup).where(Backup.status=='completed').order_by(Backup.completed_at.desc()).offset(max(retain,2))).all()
            for row in older:
                # Only this application's opaque snapshot IDs can select files in ROOT.
                if row.id in preserve or Path(row.filename).name!=row.id+'.akh':continue
                (ROOT/row.filename).unlink(missing_ok=True);(ROOT/(row.id+'.json')).unlink(missing_ok=True);row.status='expired'
            db.commit()
    except Exception:
        with SessionLocal() as db:
            row=db.get(Backup,id)
            if row:row.status='failed';row.error='สำรองข้อมูลไม่สำเร็จ ตรวจพื้นที่จัดเก็บ ฐานข้อมูล และคีย์เข้ารหัส';db.commit()
        alerts.publish('backup-failed','สำรองข้อมูลไม่สำเร็จ','ตรวจพื้นที่จัดเก็บและการเชื่อมต่อ PostgreSQL',severity='critical')

def offsite_configured():
    return bool(os.getenv('BACKUP_REMOTE_BUCKET') and os.getenv('BACKUP_REMOTE_ACCESS_KEY') and os.getenv('BACKUP_REMOTE_SECRET_KEY'))

def offsite_client():
    import boto3
    from botocore.config import Config
    return boto3.client('s3',config=Config(request_checksum_calculation='when_required',response_checksum_validation='when_required'),endpoint_url=os.getenv('BACKUP_REMOTE_ENDPOINT') or None,region_name=os.getenv('BACKUP_REMOTE_REGION','us-east-1'),aws_access_key_id=os.environ['BACKUP_REMOTE_ACCESS_KEY'],aws_secret_access_key=os.environ['BACKUP_REMOTE_SECRET_KEY'])

def replicate_offsite(id):
    """Copy the already-encrypted snapshot to a remote S3-compatible bucket and verify its size.
    A failure raises an alert but never fails the local backup."""
    if not offsite_configured():return
    try:
        bucket=os.environ['BACKUP_REMOTE_BUCKET'];prefix=os.getenv('BACKUP_REMOTE_PREFIX','ai-knowledge-hub/').lstrip('/')
        client=offsite_client();data=ROOT/(id+'.akh')
        client.upload_file(str(data),bucket,prefix+id+'.akh')
        if client.head_object(Bucket=bucket,Key=prefix+id+'.akh')['ContentLength']!=data.stat().st_size:raise RuntimeError('Remote size mismatch')
        client.upload_file(str(ROOT/(id+'.json')),bucket,prefix+id+'.json')
        keep=max(int(os.getenv('BACKUP_REMOTE_RETENTION','30')),2)
        found=[]
        for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket,Prefix=prefix):
            found+=[x for x in page.get('Contents',[]) if x['Key'].endswith('.akh')]
        found.sort(key=lambda x:x['LastModified'],reverse=True)
        for old in found[keep:]:
            client.delete_objects(Bucket=bucket,Delete={'Objects':[{'Key':old['Key']},{'Key':old['Key'][:-4]+'.json'}]})
        alerts.resolve('backup-offsite-failed')
    except Exception:
        alerts.publish('backup-offsite-failed','สำรองข้อมูลออกนอกเครื่องไม่สำเร็จ','ตรวจ BACKUP_REMOTE_* การเชื่อมต่อ และสิทธิ์ของ bucket ปลายทาง',severity='critical')

def snapshot_path(id):
    with SessionLocal() as db:
        row=db.get(Backup,id)
        if not row or row.status!='completed' or row.filename!=id+'.akh':raise ValueError('Snapshot unavailable')
        path=ROOT/row.filename;expected=row.sha256
    if not path.is_file() or digest(path)!=expected:raise ValueError('Snapshot checksum mismatch')
    return path

def read_manifest(id):
    path=snapshot_path(id)
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        archive=Path(tmp)/'data.zip';decrypt(path,archive)
        with zipfile.ZipFile(archive) as z:return json.loads(z.read('manifest.json'))

def restore_snapshot(id,target_url,target_prefix=None,live=False):
    if not live and (target_url==URL or not target_prefix):raise ValueError('Rehearsal requires isolated database and storage prefix')
    path=snapshot_path(id)
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        archive=Path(tmp)/'snapshot.zip';decrypt(path,archive)
        with zipfile.ZipFile(archive) as z:
            manifest=json.loads(z.read('manifest.json'))
            if manifest.get('format')!=1:raise ValueError('Unknown backup format')
            dump=Path(tmp)/'database.dump'
            with z.open('database.dump') as src,open(dump,'wb') as dest:shutil.copyfileobj(src,dest)
            if digest(dump)!=manifest['database_sha256']:raise ValueError('Database checksum mismatch')
            for item in manifest['files']:
                key=item['key']
                if key.startswith('/') or '..' in key.replace('\\','/').split('/'):raise ValueError('Unsafe storage key')
                data=z.read(item['entry'])
                if len(data)!=item['size'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('File checksum mismatch')
                storage.put(key if live else target_prefix+'/'+key,data)
            args,env=pg_args(target_url)
            subprocess.run(['pg_restore',*args,'--clean','--if-exists','--no-owner','--no-acl','--single-transaction','--exit-on-error',str(dump)],env=env,capture_output=True,timeout=900,check=True)
            if live:
                from . import rls;rls.apply_url(target_url)
    return manifest

def reset_restored_state():
    from .feature_models import GenerationJob
    from .models import LoginSession
    with SessionLocal() as db:
        db.execute(delete(LoginSession))
        for task in db.scalars(select(TaskRun).where(TaskRun.status.in_(['queued','processing','retry_wait']))):
            task.status='cancelled';task.lease_token='';task.lease_until=0
            if task.kind=='media':
                job=db.get(GenerationJob,task.target_id)
                if job:job.status='failed';job.error='งานจากชุดสำรอง ต้องตรวจสอบผู้ให้บริการก่อนลองใหม่'
        db.commit()
        return list(db.scalars(select(Document.id)))

def restore_live(id):
    from .jobs import redis_client
    r=redis_client();token='restore:'+secrets.token_hex(16)
    if not r.set('hub:maintenance',token,nx=True,ex=1800):return
    stop=threading.Event()
    def renew():
        while not stop.wait(30):
            try:r.eval("if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('expire',KEYS[1],1800) end",1,'hub:maintenance',token)
            except Exception:pass
    keeper=threading.Thread(target=renew,daemon=True);keeper.start()
    r.set('hub:restore-status',json.dumps({'status':'processing','backup_id':id}),ex=86400)
    try:
        r.zremrangebyscore('hub:active-chats','-inf',time.time())
        if r.zcard('hub:active-chats'):raise ValueError('Active chat streams remain')
        with SessionLocal() as db:
            if db.scalar(select(func.count()).select_from(TaskRun).where(TaskRun.status=='processing')):raise ValueError('Active jobs remain')
            # Safety snapshot before replacing the database. Never automatically overwrite without one.
            safety=Backup();db.add(safety);db.commit();safety_id=safety.id
        create_snapshot(safety_id,preserve=(id,));snapshot_path(safety_id)
        restore_snapshot(id,OWNER_URL,live=True);engine.dispose();sync_catalog()
        # Rebuild derived vector indexes; originals and relational records have already been restored.
        from .jobs import schedule_ingest
        ids=reset_restored_state()
        if r.get('hub:maintenance')==token:r.delete('hub:maintenance')
        for document_id in ids:schedule_ingest(document_id,retry=True)
        r.set('hub:restore-status',json.dumps({'status':'completed','backup_id':id,'safety_backup_id':safety_id,'reindexing':len(ids)}),ex=86400)
        alerts.publish('restore-completed','กู้คืนข้อมูลสำเร็จ','กำลังสร้างดัชนีค้นหาใหม่จากเอกสารที่กู้คืน',severity='info')
    except Exception:
        r.set('hub:restore-status',json.dumps({'status':'failed','backup_id':id,'error':'กู้คืนไม่สำเร็จ ฐานข้อมูลจะไม่ถูก commit หาก pg_restore ล้มเหลว กรุณาตรวจ safety snapshot'}),ex=86400)
        alerts.publish('restore-failed','กู้คืนข้อมูลไม่สำเร็จ','ตรวจพื้นที่จัดเก็บและ safety snapshot',severity='critical')
    finally:
        stop.set();keeper.join(timeout=2)
        if r.get('hub:maintenance')==token:r.delete('hub:maintenance')

def automatic_backup():
    hours=float(os.getenv('BACKUP_INTERVAL_HOURS','24'))
    if hours<=0:return
    with SessionLocal() as db:
        pending=db.scalar(select(Backup).where(Backup.status.in_(['queued','processing'])))
        if pending:
            if pending.status=='queued':
                from .tasks import backup_task
                backup_task.apply_async(args=[pending.id],retry=False)
            elif time.time()-datetime.fromisoformat(pending.created_at).timestamp()>3600:
                pending.status='failed';pending.error='งานสำรองหยุดกลางทาง ระบบจะสร้างชุดใหม่';db.commit()
            return
        last=db.scalar(select(Backup).where(Backup.status=='completed').order_by(Backup.completed_at.desc()).limit(1))
        if last and time.time()-datetime.fromisoformat(last.completed_at).timestamp()<hours*3600:return
        row=Backup(automatic=True);db.add(row);db.commit();id=row.id
    from .tasks import backup_task
    backup_task.apply_async(args=[id],retry=False)
