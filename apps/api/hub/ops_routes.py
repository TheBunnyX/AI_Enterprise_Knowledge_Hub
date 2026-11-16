import hashlib,json,os,time
from fastapi import APIRouter,Depends,HTTPException,Response,BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from typing import Literal
from sqlalchemy import select,delete,func,or_
from sqlalchemy.orm import Session
from .database import db_session
from .models import User,Document,Conversation,Message,Audit,now
from .feature_models import KBPolicy,DocumentVersion
from .ops_models import *
from .auth import current_user,admin,manager
from .policies import require_kb,require_document,visible_documents,group_ids,privileged
from . import storage,backups

router=APIRouter(prefix='/api')
def log(db,u,action,detail=''):
    db.add(Audit(tenant_id=u.tenant_id,user_id=u.id,actor=u.name,action=action,detail=detail));db.commit()

@router.get('/admin/operations/health')
def operations_health(u:User=Depends(admin),db:Session=Depends(db_session)):
    from .feature_models import Setting
    s=db.scalar(select(Setting).where(Setting.key=='operations-health'))
    return s.value if s else {'checks':{},'checked_at':''}

@router.post('/admin/operations/check')
def operations_check(u:User=Depends(admin)):
    from .monitoring import probe
    return probe()

def validate_principals(db,u,users,groups):
    valid_users=set(db.scalars(select(User.id).where(User.tenant_id==u.tenant_id)))
    valid_groups=set(db.scalars(select(Group.id).where(Group.tenant_id==u.tenant_id)))
    if not set(users)<=valid_users or not set(groups)<=valid_groups:raise HTTPException(422,'ผู้ใช้และกลุ่มต้องอยู่ในองค์กรเดียวกัน')

class GroupInput(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    kind:Literal['department','group']='group'
    members:list[str]=Field(default_factory=list,max_length=1000)

@router.get('/groups')
def groups(u:User=Depends(current_user),db:Session=Depends(db_session)):
    return [{'id':g.id,'name':g.name,'kind':g.kind,'members':list(db.scalars(select(GroupMember.user_id).where(GroupMember.group_id==g.id,GroupMember.tenant_id==u.tenant_id))) if privileged(u) or g.id in group_ids(db,u) else []} for g in db.scalars(select(Group).where(Group.tenant_id==u.tenant_id))]

def save_group(db,u,body,g=None):
    manager(u)
    if body.kind=='department' or (g is not None and g.kind=='department'):raise HTTPException(422,'ฝ่ายจัดการได้ที่หน้าจัดการองค์กรหรือจัดการผู้ใช้เท่านั้น')
    validate_principals(db,u,body.members,[])
    if g is not None and not privileged(u) and g.id not in group_ids(db,u):raise HTTPException(403,'จัดการได้เฉพาะแผนกหรือกลุ่มที่คุณเป็นสมาชิก')
    duplicate=db.scalar(select(Group).where(Group.tenant_id==u.tenant_id,Group.name==body.name))
    if duplicate and (not g or duplicate.id!=g.id):raise HTTPException(409,'ชื่อกลุ่มนี้มีอยู่แล้ว')
    new=g is None
    if g is None:g=Group(tenant_id=u.tenant_id,name=body.name);db.add(g);db.flush()
    g.name=body.name;g.kind=body.kind
    db.execute(delete(GroupMember).where(GroupMember.group_id==g.id,GroupMember.tenant_id==u.tenant_id))
    for id in set(body.members):db.add(GroupMember(tenant_id=u.tenant_id,group_id=g.id,user_id=id))
    if new and not privileged(u) and u.id not in body.members:db.add(GroupMember(tenant_id=u.tenant_id,group_id=g.id,user_id=u.id))
    db.commit();log(db,u,'แก้ไขแผนกหรือกลุ่ม',g.name);return {'id':g.id}

@router.post('/groups',status_code=201)
def create_group(body:GroupInput,u:User=Depends(current_user),db:Session=Depends(db_session)):return save_group(db,u,body)

@router.put('/groups/{id}')
def update_group(id:str,body:GroupInput,u:User=Depends(current_user),db:Session=Depends(db_session)):
    g=db.scalar(select(Group).where(Group.id==id,Group.tenant_id==u.tenant_id))
    if not g:raise HTTPException(404)
    return save_group(db,u,body,g)

class ResourceInput(BaseModel):
    visibility:Literal['inherit','restricted']='inherit'
    readers:list[str]=Field(default_factory=list,max_length=1000)
    writers:list[str]=Field(default_factory=list,max_length=1000)
    reader_groups:list[str]=Field(default_factory=list,max_length=1000)
    writer_groups:list[str]=Field(default_factory=list,max_length=1000)

def resource(db,u,kind,id):
    manager(u)
    if kind=='document':require_document(db,u,id,True)
    elif kind=='knowledge_base':require_kb(db,u,id,True)
    else:raise HTTPException(404)

@router.get('/access/{kind}/{id}')
def access(kind:str,id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    resource(db,u,kind,id)
    p=db.scalar(select(ResourcePolicy).where(ResourcePolicy.resource_type==kind,ResourcePolicy.resource_id==id,ResourcePolicy.tenant_id==u.tenant_id))
    return {k:getattr(p,k) for k in ResourceInput.model_fields} if p else ResourceInput().model_dump()

@router.put('/access/{kind}/{id}')
def set_access(kind:str,id:str,body:ResourceInput,u:User=Depends(current_user),db:Session=Depends(db_session)):
    resource(db,u,kind,id);validate_principals(db,u,body.readers+body.writers,body.reader_groups+body.writer_groups)
    p=db.scalar(select(ResourcePolicy).where(ResourcePolicy.resource_type==kind,ResourcePolicy.resource_id==id))
    if not p:p=ResourcePolicy(tenant_id=u.tenant_id,resource_type=kind,resource_id=id);db.add(p)
    for k,v in body.model_dump().items():setattr(p,k,v)
    if kind=='knowledge_base':
        kb=db.scalar(select(KBPolicy).where(KBPolicy.knowledge_base_id==id))
        if not kb:kb=KBPolicy(tenant_id=u.tenant_id,knowledge_base_id=id);db.add(kb)
        kb.visibility='restricted' if body.visibility=='restricted' else 'organization';kb.readers=body.readers;kb.writers=body.writers
    db.commit();log(db,u,'แก้ไขสิทธิ์ '+kind,id);return {'ok':True}

@router.get('/share/recipients')
def recipients(u:User=Depends(current_user),db:Session=Depends(db_session)):
    return {'users':[{'id':a.id,'name':a.name,'email':a.email} for a in db.scalars(select(User).where(User.tenant_id==u.tenant_id,User.active==True,User.id!=u.id))],'groups':[{'id':g.id,'name':g.name,'kind':g.kind} for g in db.scalars(select(Group).where(Group.tenant_id==u.tenant_id))]}

def owner(db,u,id):
    c=db.scalar(select(Conversation).where(Conversation.id==id,Conversation.tenant_id==u.tenant_id,Conversation.user_id==u.id))
    if not c:raise HTTPException(404)
    return c

def cited_documents(db,c):
    return {x['document_id'] for m in db.scalars(select(Message).where(Message.conversation_id==c.id,Message.tenant_id==c.tenant_id)) for x in m.citations if x.get('document_id')}

def can_read_shared(db,u,c,share,groups=None,readable=None):
    """groups/readable: the caller's group ids and readable documents, passed in when checking many shares at once."""
    if not share or share.tenant_id!=u.tenant_id or share.expires_at<=time.time():return False
    if u.id not in share.users and not (group_ids(db,u) if groups is None else groups).intersection(share.groups):return False
    return cited_documents(db,c)<=(set(visible_documents(db,u)) if readable is None else readable)

class ShareInput(BaseModel):
    users:list[str]=Field(default_factory=list,max_length=1000)
    groups:list[str]=Field(default_factory=list,max_length=1000)
    days:int=Field(default=7,ge=1,le=90)

@router.get('/conversations/{id}/sharing')
def get_sharing(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    owner(db,u,id);s=db.scalar(select(ConversationShare).where(ConversationShare.conversation_id==id,ConversationShare.tenant_id==u.tenant_id))
    return {'users':s.users,'groups':s.groups,'expires_at':s.expires_at} if s else {'users':[],'groups':[],'expires_at':None}

@router.put('/conversations/{id}/sharing')
def share(id:str,body:ShareInput,u:User=Depends(current_user),db:Session=Depends(db_session)):
    c=owner(db,u,id);validate_principals(db,u,body.users,body.groups)
    recipient_ids=set(body.users)
    if body.groups:recipient_ids.update(db.scalars(select(GroupMember.user_id).where(GroupMember.tenant_id==u.tenant_id,GroupMember.group_id.in_(body.groups))))
    refs=cited_documents(db,c)
    if not refs<=set(visible_documents(db,u)):raise HTTPException(403,'คุณไม่มีสิทธิ์ในเอกสารอ้างอิงทั้งหมดแล้ว')
    for a in db.scalars(select(User).where(User.id.in_(recipient_ids),User.tenant_id==u.tenant_id)):
        if not refs<=set(visible_documents(db,a)):raise HTTPException(409,'ผู้รับบางคนยังไม่มีสิทธิ์อ่านเอกสารอ้างอิง กรุณาปรับสิทธิ์เอกสารก่อนแชร์')
    s=db.scalar(select(ConversationShare).where(ConversationShare.conversation_id==id))
    if not s:s=ConversationShare(tenant_id=u.tenant_id,conversation_id=id,owner_id=u.id);db.add(s)
    s.users=list(set(body.users));s.groups=list(set(body.groups));s.expires_at=time.time()+body.days*86400;db.commit();log(db,u,'เปลี่ยนผู้รับบทสนทนา',id);return {'ok':True}

@router.get('/shared-conversations')
def shared_list(u:User=Depends(current_user),db:Session=Depends(db_session)):
    result=[];groups=group_ids(db,u);readable=set(visible_documents(db,u))
    for c,s in db.execute(select(Conversation,ConversationShare).join(ConversationShare,ConversationShare.conversation_id==Conversation.id).where(Conversation.tenant_id==u.tenant_id,ConversationShare.expires_at>time.time())):
        if can_read_shared(db,u,c,s,groups,readable):result.append({'id':c.id,'title':c.title,'created_at':c.created_at,'owner':db.get(User,c.user_id).name,'expires_at':s.expires_at})
    return result

@router.get('/shared-conversations/{id}')
def shared_messages(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    c=db.scalar(select(Conversation).where(Conversation.id==id,Conversation.tenant_id==u.tenant_id))
    s=db.scalar(select(ConversationShare).where(ConversationShare.conversation_id==id,ConversationShare.tenant_id==u.tenant_id))
    if not c or not can_read_shared(db,u,c,s):raise HTTPException(404,'ไม่พบบทสนทนาที่แชร์หรือสิทธิ์เอกสารเปลี่ยนไป')
    return [{'id':m.id,'role':m.role,'content':m.content,'citations':m.citations,'created_at':m.created_at} for m in db.scalars(select(Message).where(Message.conversation_id==id,Message.tenant_id==u.tenant_id).order_by(Message.created_at))]

@router.get('/documents/{id}/pdf')
def pdf(id:str,version:int|None=None,u:User=Depends(current_user),db:Session=Depends(db_session)):
    from .routes import tenant_doc
    d=tenant_doc(db,u,id);name,key=d.name,d.storage_key
    if version is not None and version!=d.version:
        v=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==id,DocumentVersion.tenant_id==u.tenant_id,DocumentVersion.version==version))
        if not v:raise HTTPException(404)
        name,key=v.name,v.storage_key
    if not name.lower().endswith('.pdf'):raise HTTPException(415,'ไฟล์นี้ไม่ใช่ PDF')
    data=storage.get(key)
    if not data.startswith(b'%PDF'):raise HTTPException(415)
    log(db,u,'เปิด PDF',id)
    return Response(data,media_type='application/pdf',headers={'Cache-Control':'private, no-store','Content-Disposition':'inline; filename="document.pdf"'})

@router.get('/notifications')
def notifications(u:User=Depends(current_user),db:Session=Depends(db_session)):
    stmt=select(SystemAlert).order_by(SystemAlert.updated_at.desc()).limit(100)
    if u.role!='SUPER_ADMIN':stmt=stmt.where(SystemAlert.tenant_id==u.tenant_id)
    if not privileged(u):stmt=stmt.where(SystemAlert.user_id==u.id)
    read={x.alert_id:x.created_at for x in db.scalars(select(AlertRead).where(AlertRead.user_id==u.id))}
    return [{'id':a.id,'title':a.title,'detail':a.detail,'severity':a.severity,'status':a.status,'updated_at':a.updated_at,'unread':read.get(a.id,'')<a.updated_at} for a in db.scalars(stmt)]

@router.post('/notifications/read')
def mark_read(u:User=Depends(current_user),db:Session=Depends(db_session)):
    for item in notifications(u,db):
        row=db.scalar(select(AlertRead).where(AlertRead.user_id==u.id,AlertRead.alert_id==item['id']))
        if not row:row=AlertRead(user_id=u.id,alert_id=item['id']);db.add(row)
        row.created_at=now()
    db.commit();return {'ok':True}

@router.get('/admin/tasks')
def task_list(u:User=Depends(admin),db:Session=Depends(db_session)):
    return [{k:getattr(r,k) for k in ('id','kind','target_id','tenant_id','status','attempts','error','updated_at')} for r in db.scalars(select(TaskRun).order_by(TaskRun.created_at.desc()).limit(100))]

@router.post('/admin/tasks/{id}/retry')
def task_retry(id:str,background:BackgroundTasks,u:User=Depends(admin),db:Session=Depends(db_session)):
    from .jobs import schedule
    r=db.get(TaskRun,id)
    if not r:raise HTTPException(404)
    if r.status not in ('failed','review_required'):raise HTTPException(409,'งานยังไม่จบหรือสำเร็จแล้ว')
    if r.kind=='media':
        from .feature_models import GenerationJob
        j=db.get(GenerationJob,r.target_id)
        if j:j.status='retrying';db.commit()
    version=r.task_key.rsplit(':',1)[-1];schedule(r.kind,r.target_id,r.tenant_id,version,background,retry=True);log(db,u,'ยืนยันลองงานใหม่',id);return {'ok':True}

@router.get('/admin/backups')
def backup_list(u:User=Depends(admin),db:Session=Depends(db_session)):
    backups.sync_catalog();db.expire_all()
    rows=[{k:getattr(b,k) for k in ('id','status','size','file_count','sha256','created_at','completed_at','error','automatic')} for b in db.scalars(select(Backup).order_by(Backup.created_at.desc()).limit(30))]
    return {'items':rows,'interval_hours':float(os.getenv('BACKUP_INTERVAL_HOURS','24')),'retention':int(os.getenv('BACKUP_RETENTION','7')),'offsite_configured':backups.offsite_configured(),'encryption_configured':bool(os.getenv('BACKUP_ENCRYPTION_KEY') or os.getenv('SECRETS_KEY'))}

@router.post('/admin/backups',status_code=202)
def backup_create(u:User=Depends(admin),db:Session=Depends(db_session)):
    if db.scalar(select(Backup).where(Backup.status.in_(['queued','processing']))):raise HTTPException(409,'มีงานสำรองข้อมูลกำลังทำอยู่')
    backups.secret();b=Backup();db.add(b);db.commit();log(db,u,'เริ่มสำรองข้อมูล',b.id)
    from .tasks import backup_task
    backup_task.apply_async(args=[b.id],retry=False);return {'id':b.id}

@router.get('/admin/backups/{id}/download')
def backup_download(id:str,u:User=Depends(admin),db:Session=Depends(db_session)):
    try:path=backups.snapshot_path(id)
    except ValueError:raise HTTPException(404,'ไม่พบ snapshot ที่พร้อมใช้งาน')
    log(db,u,'ดาวน์โหลด snapshot เข้ารหัส',id);return FileResponse(path,filename='knowledge-hub-'+id+'.akh',media_type='application/octet-stream')

@router.get('/admin/backups/{id}/restore-plan')
def restore_plan(id:str,u:User=Depends(admin),db:Session=Depends(db_session)):
    try:m=backups.read_manifest(id)
    except Exception:raise HTTPException(400,'ตรวจ snapshot ไม่สำเร็จ')
    return {'backup_id':id,'created_at':m['created_at'],'file_count':len(m['files']),'confirmation':'RESTORE '+id,'notice':'แทนที่ฐานข้อมูลและไฟล์ด้วย snapshot นี้ ระบบจะสำรองสถานะปัจจุบันก่อน และต้องเข้าสู่ระบบใหม่หลังจบ'}

class RestoreInput(BaseModel):
    confirmation:str

@router.post('/admin/backups/{id}/restore',status_code=202)
def restore(id:str,body:RestoreInput,u:User=Depends(admin),db:Session=Depends(db_session)):
    if body.confirmation!='RESTORE '+id:raise HTTPException(422,'ข้อความยืนยันไม่ตรงกับ snapshot')
    try:backups.snapshot_path(id)
    except ValueError:raise HTTPException(404)
    if db.scalar(select(TaskRun).where(TaskRun.status=='processing')):raise HTTPException(409,'กรุณารอให้งานประมวลผลที่กำลังทำอยู่จบก่อน')
    log(db,u,'ยืนยันกู้คืน snapshot',id)
    from .tasks import restore_task
    restore_task.apply_async(args=[id],retry=False);return {'status':'queued'}

@router.get('/maintenance-status')
def maintenance_status():
    from .jobs import maintenance,redis_client
    try:
        active=maintenance();raw=redis_client().get('hub:restore-status') if os.getenv('CELERY_BROKER_URL') else None
        return {'maintenance':bool(active),'restore':json.loads(raw) if raw else None}
    except Exception:raise HTTPException(503,'คิวงานไม่พร้อมใช้งาน')
