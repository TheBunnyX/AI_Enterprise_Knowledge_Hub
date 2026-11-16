"""Durable task admission and renewable leases; never blindly repeat billable media."""
import os,secrets,time,threading
from contextlib import contextmanager
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .database import SessionLocal
from .models import Document,now
from .feature_models import GenerationJob
from .ops_models import TaskRun
from . import alerts

LEASE_SECONDS=120
MAX_ATTEMPTS=5
def redis_client():
    import redis
    return redis.Redis.from_url(os.environ['CELERY_BROKER_URL'],socket_connect_timeout=2,socket_timeout=2,decode_responses=True)

def maintenance():
    if not os.getenv('CELERY_BROKER_URL'):return None
    return redis_client().get('hub:maintenance')

def enqueue(id):
    if not os.getenv('CELERY_BROKER_URL'):return
    try:
        from .tasks import execute_task
        execute_task.apply_async(args=[id],retry=False)
    except Exception:
        alerts.publish('queue-unavailable','คิวงานไม่พร้อมใช้งาน','ระบบเก็บงานไว้แล้วและจะส่งใหม่อัตโนมัติ',severity='critical')

def schedule(kind,target_id,tenant_id,version=1,background=None,retry=False):
    task_key=f'{kind}:{target_id}:{version}'
    with SessionLocal() as db:
        row=db.scalar(select(TaskRun).where(TaskRun.task_key==task_key).with_for_update())
        if row:
            if row.status in ('queued','processing','retry_wait'):return row.id
            if row.status=='completed' and not retry:return row.id
            if row.status=='review_required' and kind=='media' and not retry:return row.id
            row.status='queued';row.next_attempt=0;row.error='';row.attempts=0;row.lease_until=0;row.updated_at=now()
        else:
            row=TaskRun(task_key=task_key,kind=kind,target_id=target_id,tenant_id=tenant_id,updated_at=now());db.add(row)
        try:db.commit()
        except IntegrityError:
            db.rollback();return db.scalar(select(TaskRun.id).where(TaskRun.task_key==task_key))
        id=row.id
    if os.getenv('CELERY_BROKER_URL'):enqueue(id)
    elif background:background.add_task(execute,id)
    else:execute(id)
    return id

def schedule_ingest(id,background=None,retry=False):
    with SessionLocal() as db:
        d=db.get(Document,id)
        if not d:return None
        tenant,version=d.tenant_id,d.version
    return schedule('ingest',id,tenant,version,background,retry)

def schedule_media(id,background=None,retry=False):
    with SessionLocal() as db:
        j=db.get(GenerationJob,id)
        if not j:return None
        tenant=j.tenant_id
    return schedule('media',id,tenant,1,background,retry)

def heartbeat(id,token,stop):
    while not stop.wait(15):
        try:
            with SessionLocal() as db:
                r=db.scalar(select(TaskRun).where(TaskRun.id==id,TaskRun.lease_token==token,TaskRun.status=='processing').with_for_update())
                if not r:return
                r.lease_until=time.time()+LEASE_SECONDS;r.updated_at=now();db.commit()
        except Exception:pass

def transient(exc):
    """An outage worth retrying (network, timeout, database, 429/5xx from a service), looking through wrapped causes."""
    seen=0
    while exc is not None and seen<5:
        if isinstance(exc,(OSError,TimeoutError,ConnectionError)) or any(t in type(exc).__name__ for t in ('Connect','Timeout','Operational','Transport','ResponseHandling')):return True
        code=getattr(getattr(exc,'response',None),'status_code',None) or getattr(exc,'status_code',None)
        if isinstance(code,int) and (code==429 or code>=500):return True
        exc=exc.__cause__ or exc.__context__;seen+=1
    return False

def execute(id):
    try:
        if maintenance():return
    except Exception:return
    token=secrets.token_hex(16)
    with SessionLocal() as db:
        r=db.scalar(select(TaskRun).where(TaskRun.id==id).with_for_update())
        if not r or r.status not in ('queued','retry_wait') or r.next_attempt>time.time():return
        if r.attempts>=MAX_ATTEMPTS:r.status='failed';db.commit();return
        r.status='processing';r.attempts+=1;r.lease_token=token;r.lease_until=time.time()+LEASE_SECONDS;r.updated_at=now();db.commit()
        kind,target,tenant=r.kind,r.target_id,r.tenant_id
    stop=threading.Event();thread=threading.Thread(target=heartbeat,args=(id,token,stop),daemon=True);thread.start()
    status='completed';error=''
    try:
        if kind=='ingest':
            from .retrieval import ingest
            ingest(target,raise_errors=True)
        elif kind=='media':
            from .media import run_job
            run_job(target)
            with SessionLocal() as db:
                j=db.get(GenerationJob,target)
                if j and j.status=='failed':raise ValueError('Media provider failed')
                if j and j.status=='cancelled':status='cancelled'
        else:raise ValueError('Unknown task')
    except Exception as exc:
        # Ingestion is idempotent and can retry; media may already have been billed.
        # A retry needs the scheduler (recover) to pick the task up again, so without a queue the failure is final.
        status='retry_wait' if kind=='ingest' and transient(exc) and os.getenv('CELERY_BROKER_URL') else 'failed'
        error='ประมวลผลไม่สำเร็จ ระบบจะลองใหม่' if status=='retry_wait' else 'ประมวลผลไม่สำเร็จ กรุณาตรวจไฟล์หรือการเชื่อมต่อ'
    finally:
        stop.set();thread.join(timeout=2)
        with SessionLocal() as db:
            r=db.scalar(select(TaskRun).where(TaskRun.id==id,TaskRun.lease_token==token).with_for_update())
            if r:
                r.status=status if r.attempts<MAX_ATTEMPTS or status!='retry_wait' else 'failed';r.error=error;r.lease_until=0;r.next_attempt=time.time()+min(900,30*2**r.attempts);r.updated_at=now()
                if kind=='ingest' and r.status=='retry_wait':  # still being worked on: do not show the document as failed between attempts
                    d=db.get(Document,target)
                    if d:d.status='processing';d.error=''
                db.commit()
    if status in ('failed','retry_wait'):
        user_id=''
        if kind=='media':
            with SessionLocal() as db:
                j=db.get(GenerationJob,target);user_id=j.user_id if j else ''
        alerts.publish('job:'+id,'งานประมวลผลไม่สำเร็จ',error,tenant,user_id,target)
    else:alerts.resolve('job:'+id)

def recover():
    queued=[];review=[]
    with SessionLocal() as db:
        rows=db.scalars(select(TaskRun).where(TaskRun.status.in_(['processing','queued','retry_wait'])).with_for_update()).all()
        for r in rows:
            if r.attempts>=MAX_ATTEMPTS and (r.status!='processing' or r.lease_until<time.time()):
                r.status='failed';r.error='ครบจำนวนครั้งที่ลองใหม่แล้ว';r.updated_at=now()
                review.append((r.id,r.tenant_id,'',r.target_id));continue
            if r.status=='processing' and r.lease_until<time.time():
                if r.kind=='media':
                    j=db.get(GenerationJob,r.target_id)
                    if j and j.kind=='video' and j.provider_job_id:
                        j.status='retrying';r.status='queued'
                    else:
                        r.status='review_required';r.error='งานหยุดกลางทาง ผู้ให้บริการอาจรับคำสั่งแล้ว ต้องยืนยันก่อนลองใหม่'
                        if j:j.status='failed';j.error=r.error
                        review.append((r.id,r.tenant_id,j.user_id if j else '',r.target_id));continue
                else:r.status='queued'
                r.lease_until=0;r.updated_at=now()
            if r.status in ('queued','retry_wait') and r.next_attempt<=time.time() and r.attempts<MAX_ATTEMPTS:queued.append(r.id)
        db.commit()
    for id in queued:enqueue(id)
    for id,tenant,user,target in review:alerts.publish('job:'+id,'งานต้องตรวจสอบก่อนลองใหม่','ป้องกันการสร้างสื่อและคิดค่าบริการซ้ำ',tenant,user,target)
    return {'requeued':len(queued),'review_required':len(review)}
