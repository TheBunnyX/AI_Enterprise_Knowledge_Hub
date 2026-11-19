"""Live up/down probes for the six infrastructure services shown in the sidebar.

Each probe is short-timeout and runs in parallel; results are cached briefly so many open tabs don't hammer the services.
True = up, False = down, None = not used in this deployment.
"""
import os,socket,threading,time
from concurrent.futures import ThreadPoolExecutor,wait
import httpx
from sqlalchemy import select
from .database import SessionLocal

SERVICES=[('api','API'),('database','ฐานข้อมูล'),('storage','จัดเก็บเอกสาร'),('vector','ค้นหาเวกเตอร์'),('queue','คิวประมวลผล'),('antivirus','Antivirus')]
TIMEOUT=2.
TTL=10.
_cache={'at':0.,'data':None};_lock=threading.Lock()

def _database():
    with SessionLocal() as db:db.execute(select(1))
    return True

def _storage():
    if not os.getenv('S3_ENDPOINT'):return os.access(os.getenv('DATA_DIR','/data'),os.W_OK)
    import boto3
    from botocore.config import Config
    boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT'],aws_access_key_id=os.environ['S3_ACCESS_KEY'],aws_secret_access_key=os.environ['S3_SECRET_KEY'],
                 config=Config(connect_timeout=TIMEOUT,read_timeout=TIMEOUT,retries={'max_attempts':0})).head_bucket(Bucket=os.getenv('S3_BUCKET','knowledge'))
    return True

def _vector():
    url=os.getenv('QDRANT_URL')
    if not url:return None
    return httpx.get(url.rstrip('/')+'/readyz',timeout=TIMEOUT).status_code==200

def _queue():
    url=os.getenv('CELERY_BROKER_URL')
    if not url:return None
    import redis
    return bool(redis.Redis.from_url(url,socket_timeout=TIMEOUT,socket_connect_timeout=TIMEOUT).ping())

def _antivirus():
    from . import antivirus
    host=os.getenv('CLAMAV_HOST')
    if not host or not antivirus.enabled():return None
    with socket.create_connection((host,int(os.getenv('CLAMAV_PORT','3310'))),timeout=TIMEOUT) as s:
        s.sendall(b'zPING\0');return s.recv(100).startswith(b'PONG')

PROBES={'api':lambda:True,'database':_database,'storage':_storage,'vector':_vector,'queue':_queue,'antivirus':_antivirus}

def _run(fn):
    try:return fn()
    except Exception:return False

def check():
    with _lock:
        if _cache['data'] and time.monotonic()-_cache['at']<TTL:return _cache['data']
    # Hard overall deadline: a stopped container can stall in DNS longer than any per-call timeout; unfinished = down.
    pool=ThreadPoolExecutor(len(PROBES))
    futures={k:pool.submit(_run,fn) for k,fn in PROBES.items()}
    wait(futures.values(),timeout=TIMEOUT+.5)
    pool.shutdown(wait=False)
    results={k:f.result() if f.done() else False for k,f in futures.items()}
    data={'checked_at':time.time(),'services':[{'key':k,'label':label,'up':results[k]} for k,label in SERVICES]}
    with _lock:_cache.update(at=time.monotonic(),data=data)
    return data
