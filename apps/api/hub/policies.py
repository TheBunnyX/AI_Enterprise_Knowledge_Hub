from fastapi import HTTPException
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from .models import KnowledgeBase, AIModel, Document, Usage
from .feature_models import KBPolicy, DocumentState, ModelPolicy
from .ops_models import Group, GroupMember, ResourcePolicy

def privileged(u):return u.role=='SUPER_ADMIN'

def month_spend(db,user_id):
    """USD a user has spent this calendar month, including reservations for requests still running."""
    month=datetime.now(timezone.utc).strftime('%Y-%m')
    return float(db.scalar(select(func.coalesce(func.sum(Usage.cost),0)).where(Usage.user_id==user_id,Usage.created_at.startswith(month))))

PERIODS=('day','week','month')
PERIOD_TH={'day':'รายวัน','week':'รายสัปดาห์','month':'รายเดือน'}

def period_start(period,now=None):
    """First moment (UTC date string) of the current day, ISO week (Monday) or calendar month."""
    d=(now or datetime.now(timezone.utc)).date()
    if period=='day':return d.isoformat()
    if period=='week':return (d-timedelta(days=d.weekday())).isoformat()
    return d.replace(day=1).isoformat()

def period_spend(db,user_id,period='month'):
    """USD a user has spent in the current day, week or month (UTC), including reservations still running."""
    return float(db.scalar(select(func.coalesce(func.sum(Usage.cost),0)).where(Usage.user_id==user_id,Usage.created_at>=period_start(period))))

def user_spend(db,u):return period_spend(db,u.id,u.budget_period or 'month')

def enforce_user_quota(db,u):
    if u.monthly_budget and user_spend(db,u)>=u.monthly_budget:raise HTTPException(429,f'ใช้งบประมาณ{PERIOD_TH.get(u.budget_period,"รายเดือน")}ของคุณครบแล้ว กรุณาติดต่อผู้ดูแล')
def visible_kbs(db,u,write=False):
    bases=db.scalars(select(KnowledgeBase).where(KnowledgeBase.tenant_id==u.tenant_id)).all()
    policies={p.knowledge_base_id:p for p in db.scalars(select(KBPolicy).where(KBPolicy.tenant_id==u.tenant_id))}
    groups=group_ids(db,u)
    mine=department_ids(db,u)
    extras={p.resource_id:p for p in db.scalars(select(ResourcePolicy).where(ResourcePolicy.tenant_id==u.tenant_id,ResourcePolicy.resource_type=='knowledge_base'))}
    def allowed(b):
        if privileged(u):return True
        p=policies.get(b.id)
        extra=extras.get(b.id)
        if write:
            # A department's knowledge base is managed by that department's admins; one with no department by any department admin.
            # Everyone else needs an explicit grant: being able to read a knowledge base never means being able to change it.
            if u.role=='DEPARTMENT_ADMIN' and (b.department_id in mine if b.department_id else True):return True
            group_allowed=bool(extra and groups.intersection(extra.writer_groups))
            return group_allowed or bool(p and u.id in p.writers)
        if not p or p.visibility=='organization' or b.department_id in mine:return True
        group_allowed=bool(extra and groups.intersection(extra.reader_groups+extra.writer_groups))
        return group_allowed or u.id in p.readers+p.writers
    return [b.id for b in bases if allowed(b)]

def require_kb(db,u,id,write=False):
    if id not in visible_kbs(db,u,write):raise HTTPException(404,'ไม่พบคลังความรู้หรือไม่มีสิทธิ์เข้าถึง')

def deleted_ids():return select(DocumentState.document_id).where(DocumentState.deleted_at!='')

def available_models(db,u,category=None):
    stmt=select(AIModel).where(AIModel.enabled==True)
    if category:stmt=stmt.where(AIModel.category==category)
    policy=db.scalar(select(ModelPolicy).where(ModelPolicy.tenant_id==u.tenant_id))
    if policy:stmt=stmt.where(AIModel.id.in_(policy.allowed_models))
    return db.scalars(stmt).all()

def allow_new_model(db,model):
    """A tenant policy lists the models an organisation may use. One that already lists every model was meant to allow
    them all, so a model registered later joins it; a deliberately narrower list is left alone."""
    from .feature_models import ModelPolicy as Policy
    others=set(db.scalars(select(AIModel.id)))-{model.id}
    for p in db.scalars(select(Policy)):
        if others<=set(p.allowed_models) and model.id not in p.allowed_models:p.allowed_models=[*p.allowed_models,model.id]
    db.commit()

def usable(db,m):
    from . import gateway
    return gateway.configured(db,m.provider)

def choose_model(db,u,category,id=None):
    models=available_models(db,u,category)
    if id:
        match=next((m for m in models if m.id==id),None)
        if not match:raise HTTPException(403,'โมเดลนี้ไม่ได้รับอนุญาตสำหรับองค์กร')
        return match
    policy=db.scalar(select(ModelPolicy).where(ModelPolicy.tenant_id==u.tenant_id))
    if policy and policy.default_model:
        match=next((m for m in models if m.id==policy.default_model and usable(db,m)),None)
        if match:return match
    if not models:raise HTTPException(503,'ยังไม่มีโมเดลที่เปิดใช้งานสำหรับบริการนี้')
    return next((m for m in models if usable(db,m)),models[0])  # skip models whose provider has no key yet


def department_ids(db,u):
    """The departments (access groups of kind 'department') this user belongs to."""
    return set(db.scalars(select(GroupMember.group_id).join(Group,Group.id==GroupMember.group_id).where(Group.tenant_id==u.tenant_id,Group.kind=='department',GroupMember.user_id==u.id)))

def group_ids(db,u):
    return set(db.scalars(select(GroupMember.group_id).where(GroupMember.tenant_id==u.tenant_id,GroupMember.user_id==u.id)))

def visible_documents(db,u,write=False):
    # A document is in reach when its knowledge base is readable; writing it needs write on the knowledge base, or an explicit grant on the document itself.
    writable_bases=set(visible_kbs(db,u,True)) if write else set()
    rows=db.execute(select(Document.id,Document.knowledge_base_id).where(Document.tenant_id==u.tenant_id,Document.knowledge_base_id.in_(visible_kbs(db,u)),~Document.id.in_(deleted_ids()))).all()  # ids only: this runs on most requests
    docs=[id for id,kb in rows]
    if privileged(u):return docs
    base_of=dict(rows)
    groups=group_ids(db,u)
    policies={p.resource_id:p for p in db.scalars(select(ResourcePolicy).where(ResourcePolicy.tenant_id==u.tenant_id,ResourcePolicy.resource_type=='document'))}
    result=[]
    for id in docs:
        p=policies.get(id)
        if not p or p.visibility=='inherit':
            if not write or base_of[id] in writable_bases:result.append(id)
            continue
        users=p.writers if write else p.readers+p.writers
        permitted=p.writer_groups if write else p.reader_groups+p.writer_groups
        if u.id in users or groups.intersection(permitted):result.append(id)
    return result

def require_document(db,u,id,write=False):
    if id not in visible_documents(db,u,write):raise HTTPException(404,'ไม่พบเอกสารหรือไม่มีสิทธิ์เข้าถึง')

def spending_scope(db,u):
    """Whose usage and cost this user may see: ('organization', None) for a Super Admin, ('department', user ids) for a
    department admin (the members of the departments they belong to, themselves included), ('self', [own id]) otherwise."""
    if u.role=='SUPER_ADMIN':return 'organization',None
    if u.role=='DEPARTMENT_ADMIN':
        own=select(GroupMember.group_id).join(Group,Group.id==GroupMember.group_id).where(Group.tenant_id==u.tenant_id,Group.kind=='department',GroupMember.user_id==u.id)
        members=set(db.scalars(select(GroupMember.user_id).where(GroupMember.tenant_id==u.tenant_id,GroupMember.group_id.in_(own))))
        return 'department',sorted(members|{u.id})
    return 'self',[u.id]
