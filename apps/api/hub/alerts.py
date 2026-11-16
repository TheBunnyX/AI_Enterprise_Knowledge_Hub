from sqlalchemy import select
from .database import SessionLocal
from .ops_models import SystemAlert
from .models import now

def publish(key,title,detail='',tenant_id='',user_id='',resource_id='',severity='warning'):
    with SessionLocal() as db:
        a=db.scalar(select(SystemAlert).where(SystemAlert.alert_key==key))
        if a and a.status=='active' and a.title==title and a.detail==detail and a.severity==severity:return
        if not a:a=SystemAlert(alert_key=key,title=title);db.add(a)
        a.title=title;a.detail=detail;a.tenant_id=tenant_id;a.user_id=user_id;a.resource_id=resource_id;a.severity=severity;a.status='active';a.updated_at=now();db.commit()

def resolve(key):
    with SessionLocal() as db:
        a=db.scalar(select(SystemAlert).where(SystemAlert.alert_key==key))
        if a and a.status!='resolved':a.status='resolved';a.updated_at=now();db.commit()
