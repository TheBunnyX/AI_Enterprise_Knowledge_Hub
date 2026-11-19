import os
import httpx
from sqlalchemy import text
from .database import engine
from . import alerts,antivirus,storage

def probe():
    checks={}
    def check(name,fn):
        try:fn();checks[name]='healthy';alerts.resolve('service:'+name)
        except Exception:checks[name]='unavailable';alerts.publish('service:'+name,'บริการ '+name+' ไม่พร้อมใช้งาน','ตรวจการเชื่อมต่อและสถานะบริการ',severity='critical')
    def database():
        with engine.connect() as c:c.execute(text('SELECT 1'))
    check('database',database)
    if os.getenv('CELERY_BROKER_URL'):
        from .jobs import redis_client
        check('redis',lambda:redis_client().ping())
        def worker():
            if checks['redis']!='healthy':raise ConnectionError()
            from .tasks import celery
            queues=celery.control.inspect(timeout=3).active_queues() or {}
            if not any(any(q['name']=='celery' for q in qs) for qs in queues.values()):raise ConnectionError()
        check('worker',worker)
    if os.getenv('QDRANT_URL'):check('qdrant',lambda:httpx.get(os.environ['QDRANT_URL']+'/readyz',timeout=5).raise_for_status())
    if os.getenv('S3_ENDPOINT'):check('storage',lambda:storage.s3().head_bucket(Bucket=os.getenv('S3_BUCKET','knowledge')))
    if os.getenv('CLAMAV_HOST'):
        if antivirus.enabled():check('antivirus',antivirus.ping)
        else:alerts.resolve('service:antivirus')  # switched off on purpose: nothing to watch
    from .feature_models import Setting
    from .database import SessionLocal
    from .models import now
    with SessionLocal() as db:
        s=db.query(Setting).filter(Setting.key=='operations-health').first()
        if not s:s=Setting(key='operations-health');db.add(s)
        s.value={'checks':checks,'checked_at':now()};db.commit()
    return checks
