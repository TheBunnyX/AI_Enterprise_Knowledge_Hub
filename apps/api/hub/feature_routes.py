import hashlib, json, os, secrets, time
from datetime import datetime,timezone,timedelta
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form, File, UploadFile, Response, Query, Request
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session
from .database import db_session
from .models import *
from .feature_models import *
from .auth import current_user,admin,manager,passwords,public_user
from .policies import require_kb,visible_kbs,deleted_ids,choose_model,require_document,enforce_user_quota,privileged
from .ops_models import Group
from . import gateway, storage
from .media import public_job,run_job
router=APIRouter(prefix='/api')

def log(db,u,action,detail=''):
    db.add(Audit(tenant_id=u.tenant_id,user_id=u.id,actor=u.name,action=action,detail=detail));db.commit()

class GatewayInput(BaseModel):
    url:str=Field(max_length=500)
    api_key:str|None=Field(default=None,max_length=1000)

@router.get('/admin/gateway')
def get_gateway(u:User=Depends(admin),db:Session=Depends(db_session)):
    url,key=gateway.configuration(db);return {'url':url,'key_configured':bool(key),'encryption_configured':bool(os.getenv('SECRETS_KEY'))}

@router.put('/admin/gateway')
def save_gateway(body:GatewayInput,u:User=Depends(admin),db:Session=Depends(db_session)):
    if body.url:gateway.validate_url(body.url)
    s=db.scalar(select(Setting).where(Setting.key=='gateway'))
    if not s:s=Setting(key='gateway',value={});db.add(s)
    value=dict(s.value);value['url']=body.url.rstrip('/')
    if body.api_key is not None:value['encrypted_key']=gateway.cipher().encrypt(body.api_key.encode()).decode() if body.api_key else ''
    s.value=value;db.commit();log(db,u,'แก้ไข Gateway');return {'ok':True}

@router.post('/admin/gateway/test')
async def test_gateway(u:User=Depends(admin),db:Session=Depends(db_session)):
    import httpx
    url,key=gateway.configuration(db)
    if not url:raise HTTPException(503,'ยังไม่ได้ตั้งค่า Gateway')
    start=time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r=await client.get(url+'/models',headers=gateway.headers(key));r.raise_for_status();ids=[m['id'] for m in r.json().get('data',[])]
    except (httpx.HTTPError,ValueError,KeyError):raise HTTPException(502,'เชื่อมต่อ Gateway ไม่สำเร็จ ตรวจ URL และ API key')
    log(db,u,'ทดสอบ Gateway');return {'ok':True,'models':ids,'latency_ms':round((time.monotonic()-start)*1000)}

class ProviderInput(BaseModel):
    url:str=Field(default='',max_length=500)
    api_key:str=Field(min_length=1,max_length=1000)

def provider_name(name):
    if not 1<=len(name)<=60 or not name.strip():raise HTTPException(422,'ชื่อผู้ให้บริการไม่ถูกต้อง')
    return name.strip()

@router.get('/admin/providers')
def list_providers(u:User=Depends(admin),db:Session=Depends(db_session)):
    saved=gateway.provider_settings(db)
    names=list(dict.fromkeys(list(gateway.KNOWN_PROVIDERS)+list(saved)))
    return [{'name':n,'url':(saved.get(n) or {}).get('url') or gateway.KNOWN_PROVIDERS.get(n,''),'key_configured':bool(gateway.env_key(n) or (saved.get(n) or {}).get('encrypted_key')),'source':'env' if gateway.env_key(n) else 'database'} for n in names]

@router.put('/admin/providers/{name}')
def save_provider(name:str,body:ProviderInput,u:User=Depends(admin),db:Session=Depends(db_session)):
    name=provider_name(name)
    if gateway.env_key(name):raise HTTPException(409,'API key ของ '+name+' ตั้งไว้ในไฟล์ .env แล้ว แก้ที่ไฟล์นั้นแล้วรีสตาร์ต api')
    url=body.url.rstrip('/') or gateway.KNOWN_PROVIDERS.get(name,'')
    if not url:raise HTTPException(422,'ผู้ให้บริการนี้ต้องระบุ URL')
    gateway.validate_url(url)
    s=db.scalar(select(Setting).where(Setting.key=='providers'))
    if not s:s=Setting(key='providers',value={});db.add(s)
    s.value={**s.value,name:{'url':url,'encrypted_key':gateway.cipher().encrypt(body.api_key.encode()).decode()}};db.commit();log(db,u,'ตั้งค่าผู้ให้บริการ',name);return {'ok':True}

@router.delete('/admin/providers/{name}')
def delete_provider(name:str,u:User=Depends(admin),db:Session=Depends(db_session)):
    s=db.scalar(select(Setting).where(Setting.key=='providers'))
    if s and name in s.value:s.value={k:v for k,v in s.value.items() if k!=name};db.commit();log(db,u,'ลบผู้ให้บริการ',name)
    return {'ok':True}

@router.post('/admin/providers/{name}/test')
async def test_provider(name:str,u:User=Depends(admin),db:Session=Depends(db_session)):
    import httpx
    if not (gateway.env_key(name) or (gateway.provider_settings(db).get(name) or {}).get('encrypted_key')):raise HTTPException(404,'ยังไม่ได้ตั้ง API key ของผู้ให้บริการนี้')
    url,key=gateway.configuration(db,name);start=time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r=await client.get(url+'/models',headers=gateway.headers(key));r.raise_for_status();ids=[m['id'] for m in r.json().get('data',[])]
    except (httpx.HTTPError,ValueError,KeyError):raise HTTPException(502,'เชื่อมต่อผู้ให้บริการไม่สำเร็จ ตรวจ API key')
    return {'ok':True,'models':ids,'latency_ms':round((time.monotonic()-start)*1000)}

class AccessInput(BaseModel):
    visibility:Literal['organization','restricted']='organization'
    readers:list[str]=Field(default_factory=list,max_length=1000)
    writers:list[str]=Field(default_factory=list,max_length=1000)

@router.get('/tenant/users')
def tenant_users(u:User=Depends(current_user),db:Session=Depends(db_session)):
    manager(u);return [public_user(a) for a in db.scalars(select(User).where(User.tenant_id==u.tenant_id))]

@router.get('/knowledge-bases/{id}/access')
def get_access(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    manager(u);require_kb(db,u,id,True)
    p=db.scalar(select(KBPolicy).where(KBPolicy.knowledge_base_id==id,KBPolicy.tenant_id==u.tenant_id))
    return {'visibility':p.visibility,'readers':p.readers,'writers':p.writers} if p else AccessInput().model_dump()

@router.put('/knowledge-bases/{id}/access')
def set_access(id:str,body:AccessInput,u:User=Depends(current_user),db:Session=Depends(db_session)):
    manager(u);require_kb(db,u,id,True)
    valid=set(db.scalars(select(User.id).where(User.tenant_id==u.tenant_id)))
    if not set(body.readers+body.writers)<=valid:raise HTTPException(422,'ผู้ใช้ทุกคนต้องอยู่ในองค์กรเดียวกัน')
    p=db.scalar(select(KBPolicy).where(KBPolicy.knowledge_base_id==id))
    if not p:p=KBPolicy(tenant_id=u.tenant_id,knowledge_base_id=id);db.add(p)
    for k,v in body.model_dump().items():setattr(p,k,v)
    db.commit();log(db,u,'เปลี่ยนสิทธิ์คลังความรู้',id);return {'ok':True}

@router.get('/documents-trash')
def trash(u:User=Depends(current_user),db:Session=Depends(db_session)):
    manager(u)
    rows=db.execute(select(Document,DocumentState).join(DocumentState,DocumentState.document_id==Document.id).where(Document.tenant_id==u.tenant_id,DocumentState.deleted_at!=''))
    return [{'id':d.id,'name':d.name,'deleted_at':s.deleted_at} for d,s in rows]

@router.post('/documents/{id}/restore')
def restore(id:str,background:BackgroundTasks,u:User=Depends(current_user),db:Session=Depends(db_session)):
    manager(u);d=db.scalar(select(Document).where(Document.id==id,Document.tenant_id==u.tenant_id))
    if not d:raise HTTPException(404)
    require_kb(db,u,d.knowledge_base_id,True)
    s=db.scalar(select(DocumentState).where(DocumentState.document_id==id,DocumentState.tenant_id==u.tenant_id))
    if not s or not s.deleted_at:raise HTTPException(400,'เอกสารไม่ได้อยู่ในถังขยะ')
    s.deleted_at='';d.status='processing';db.commit()
    from .jobs import schedule_ingest
    schedule_ingest(id,background,retry=True)
    log(db,u,'กู้คืนเอกสาร',d.name);return {'ok':True}

@router.get('/documents/{id}/versions')
def versions(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    from .routes import tenant_doc
    d=tenant_doc(db,u,id)
    rows=db.scalars(select(DocumentVersion).where(DocumentVersion.document_id==id,DocumentVersion.tenant_id==u.tenant_id).order_by(DocumentVersion.version.desc()))
    return [{'id':v.id,'version':v.version,'name':v.name,'size':v.size,'created_at':v.created_at} for v in rows]+[{'id':'current','version':d.version,'name':d.name,'size':d.size,'created_at':d.created_at}]

@router.get('/documents/{id}/versions/{version_id}/download')
def version_download(id:str,version_id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    from .routes import tenant_doc
    tenant_doc(db,u,id)
    v=db.scalar(select(DocumentVersion).where(DocumentVersion.id==version_id,DocumentVersion.document_id==id,DocumentVersion.tenant_id==u.tenant_id))
    if not v:raise HTTPException(404)
    from urllib.parse import quote
    return Response(storage.get(v.storage_key),media_type='application/octet-stream',headers={'Content-Disposition':f"attachment; filename*=UTF-8''{quote(v.name)}"})

@router.post('/documents/{id}/versions')
async def add_version(id:str,background:BackgroundTasks,file:UploadFile=File(...),u:User=Depends(current_user),db:Session=Depends(db_session)):
    from .routes import tenant_doc
    from .uploads import read_validated
    from .retrieval import ingest
    d=tenant_doc(db,u,id);require_document(db,u,id,True)
    name,data=await read_validated(file);digest=hashlib.sha256(data).hexdigest()
    duplicate=db.scalar(select(Document).where(Document.tenant_id==u.tenant_id,Document.sha256==digest))
    if duplicate:raise HTTPException(409,'มีเนื้อหาไฟล์นี้อยู่แล้วในองค์กร')
    if d.status=='processing':raise HTTPException(409,'กรุณารอเวอร์ชันปัจจุบันประมวลผลก่อน')
    key=f'{u.tenant_id}/{secrets.token_hex(16)}';storage.put(key,data)
    db.add(DocumentVersion(tenant_id=u.tenant_id,document_id=d.id,version=d.version,name=d.name,size=d.size,sha256=d.sha256,storage_key=d.storage_key))
    d.name=name;d.size=len(data);d.sha256=digest;d.storage_key=key;d.version+=1;d.status='processing';d.error='';db.commit()
    from .jobs import schedule_ingest
    schedule_ingest(id,background,retry=True)
    log(db,u,'เพิ่มเวอร์ชันเอกสาร',d.name);return {'id':id,'version':d.version}

class ProfileInput(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    default_model:str=''
    notifications:bool=True

@router.get('/account/preferences')
def preferences(u:User=Depends(current_user),db:Session=Depends(db_session)):
    p=db.scalar(select(UserPreference).where(UserPreference.user_id==u.id));return {'name':u.name,'default_model':'','notifications':True}|(p.value if p else {})

@router.put('/account/preferences')
def save_preferences(body:ProfileInput,u:User=Depends(current_user),db:Session=Depends(db_session)):
    if body.default_model:choose_model(db,u,'LLM',body.default_model)
    p=db.scalar(select(UserPreference).where(UserPreference.user_id==u.id))
    if not p:p=UserPreference(user_id=u.id);db.add(p)
    u.name=body.name;p.value=body.model_dump();db.commit();log(db,u,'แก้ไขบัญชี');return public_user(u)

@router.get('/account/sessions')
def sessions(request:Request,u:User=Depends(current_user),db:Session=Depends(db_session)):
    token_hash=hashlib.sha256(request.cookies.get('hub_session','').encode()).hexdigest()
    return [{'id':s.id,'created_at':s.created_at,'expires_at':datetime.fromtimestamp(s.expires,timezone.utc).isoformat(),'current':s.token_hash==token_hash,'ip':s.ip} for s in db.scalars(select(LoginSession).where(LoginSession.user_id==u.id,LoginSession.expires>time.time()))]

@router.delete('/account/sessions/{id}')
def revoke(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    s=db.scalar(select(LoginSession).where(LoginSession.id==id,LoginSession.user_id==u.id))
    if not s:raise HTTPException(404)
    db.delete(s);db.commit();return {'ok':True}

class UserRoleInput(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    name_en:str=Field('',max_length=100)
    role:Literal['SUPER_ADMIN','DEPARTMENT_ADMIN','USER']

@router.put('/admin/users/{id}')
def edit_user(id:str,body:UserRoleInput,u:User=Depends(admin),db:Session=Depends(db_session)):
    a=db.get(User,id)
    if not a:raise HTTPException(404)
    if a.id==u.id and body.role!='SUPER_ADMIN':raise HTTPException(400,'ไม่สามารถลดสิทธิ์บัญชีตนเอง')
    from .ops_models import Group,GroupMember
    if body.role!='SUPER_ADMIN' and not db.scalar(select(func.count()).select_from(GroupMember).join(Group,Group.id==GroupMember.group_id).where(GroupMember.user_id==a.id,Group.kind=='department')):raise HTTPException(422,'ผู้ใช้ที่ไม่ใช่ Super Admin ต้องอยู่ในฝ่ายอย่างน้อยหนึ่งฝ่ายก่อน')
    a.name=body.name;a.name_en=body.name_en.strip();a.role=body.role;db.execute(delete(LoginSession).where(LoginSession.user_id==id));db.commit();log(db,u,'เปลี่ยนบทบาทผู้ใช้',a.email);return {'ok':True}

class PolicyInput(BaseModel):
    allowed_models:list[str]=Field(default_factory=list,max_length=500)
    default_model:str=''
    monthly_budget:float=Field(default=0,ge=0)

@router.get('/admin/organizations/{id}/policy')
def get_policy(id:str,u:User=Depends(admin),db:Session=Depends(db_session)):
    if not db.get(Organization,id):raise HTTPException(404)
    p=db.scalar(select(ModelPolicy).where(ModelPolicy.tenant_id==id))
    return {'allowed_models':p.allowed_models,'default_model':p.default_model,'monthly_budget':p.monthly_budget} if p else {'allowed_models':list(db.scalars(select(AIModel.id))),'default_model':'','monthly_budget':0}

@router.put('/admin/organizations/{id}/policy')
def save_policy(id:str,body:PolicyInput,u:User=Depends(admin),db:Session=Depends(db_session)):
    if not db.get(Organization,id):raise HTTPException(404)
    valid=set(db.scalars(select(AIModel.id)))
    if not set(body.allowed_models)<=valid or body.default_model and body.default_model not in body.allowed_models:raise HTTPException(422,'นโยบายโมเดลไม่ถูกต้อง')
    p=db.scalar(select(ModelPolicy).where(ModelPolicy.tenant_id==id))
    if not p:p=ModelPolicy(tenant_id=id);db.add(p)
    for k,v in body.model_dump().items():setattr(p,k,v)
    db.commit();log(db,u,'เปลี่ยนนโยบายโมเดลและงบประมาณ',id);return {'ok':True}

@router.get('/billing/summary')
def billing(u:User=Depends(current_user),db:Session=Depends(db_session)):
    """This month's spend. budget_exceeded always reflects the organisation budget, because that is what blocks requests;
    the amounts are the organisation's only for a Super Admin - everyone else gets their own scope (policies.spending_scope)."""
    from .policies import spending_scope
    month=datetime.now(timezone.utc).strftime('%Y-%m')
    spent=db.scalar(select(func.coalesce(func.sum(Usage.cost),0)).where(Usage.tenant_id==u.tenant_id,Usage.created_at.startswith(month)))
    p=db.scalar(select(ModelPolicy).where(ModelPolicy.tenant_id==u.tenant_id));budget=p.monthly_budget if p else 0
    exceeded=bool(budget and spent>=budget)
    jobs=select(func.count()).select_from(GenerationJob).where(GenerationJob.tenant_id==u.tenant_id,GenerationJob.status=='completed',GenerationJob.cost_known==False,GenerationJob.created_at.startswith(month))
    kind,people_ids=spending_scope(db,u)
    if people_ids is not None:
        spent=db.scalar(select(func.coalesce(func.sum(Usage.cost),0)).where(Usage.tenant_id==u.tenant_id,Usage.user_id.in_(people_ids),Usage.created_at.startswith(month)))
        budget=u.monthly_budget if kind=='self' else 0;jobs=jobs.where(GenerationJob.user_id.in_(people_ids))
    return {'month':month,'spent':spent,'budget':budget,'budget_exceeded':exceeded,'unpriced_media_jobs':db.scalar(jobs),'scope':kind}

@router.get('/media/model-options')
def media_model_options(model_id:str,raw:bool=False,u:User=Depends(current_user),db:Session=Depends(db_session)):
    m=db.get(AIModel,model_id)
    if not m or m.category not in ('Image','Video'):raise HTTPException(404,'ไม่พบโมเดล')
    choose_model(db,u,m.category,m.id)
    url,_=gateway.configuration(db,m.provider)
    if not url:return {}
    import httpx
    from .media import model_options
    from .media import apply_limits
    with httpx.Client(timeout=15,follow_redirects=False) as c:found=model_options(c,url,m.provider,m.category.lower(),m.api_id)
    # Administrators editing the model (raw=true) see everything the model offers; everyone else only what is allowed.
    return found if raw and u.role=='SUPER_ADMIN' else apply_limits(found,m.media_limits)

@router.post('/media/jobs',status_code=202)
async def create_media(background:BackgroundTasks,kind:str=Form(...),model_id:str=Form(...),prompt:str=Form(''),options:str=Form('{}'),file:UploadFile|None=File(None),u:User=Depends(current_user),db:Session=Depends(db_session)):
    categories={'image':'Image','video':'Video','stt':'STT','tts':'TTS'}
    if kind not in categories:raise HTTPException(422,'ชนิดสื่อไม่ถูกต้อง')
    model=choose_model(db,u,categories[kind],model_id)
    if not gateway.configured(db,model.provider):raise HTTPException(503,'กรุณาตั้งค่า Gateway และ API key ก่อนสร้างสื่อ')
    enforce_user_quota(db,u)
    summary=billing(u,db)
    if summary['budget_exceeded']:raise HTTPException(429,'เกินงบประมาณรายเดือนขององค์กร')
    from . import savings
    sp=savings.policy(db,u.tenant_id);savings.enforce_limits(db,u,sp)
    if savings.media_remaining(db,u,sp)==0:raise HTTPException(429,f'สร้างสื่อครบ {sp["media_daily_limit"]} งานต่อวันแล้ว กรุณาลองใหม่พรุ่งนี้')
    estimate=savings.estimate_cost(db,u.tenant_id,model.id)
    if sp['media_daily_usd'] and kind in ('image','video') and savings.media_spent_today(db,u)+(estimate or 0)>sp['media_daily_usd']:raise HTTPException(429,f'ใช้งบสร้างสื่อวันนี้ครบ ${sp["media_daily_usd"]:g} แล้ว กรุณาลองใหม่พรุ่งนี้หรือติดต่อผู้ดูแลระบบ')
    needs_approval=bool(sp['media_approval_usd'] and estimate is not None and estimate>=sp['media_approval_usd'])
    pending=db.scalar(select(func.count()).select_from(GenerationJob).where(GenerationJob.user_id==u.id,GenerationJob.status.in_(['queued','processing','retrying','awaiting_approval'])))
    if pending>=3:raise HTTPException(429,'มีงานกำลังทำอยู่ครบ 3 งาน กรุณารอก่อน')
    if len(prompt)>6000 or kind!='stt' and not prompt.strip():raise HTTPException(422,'กรุณาระบุข้อความไม่เกิน 6,000 ตัวอักษร')
    try:
        opts=json.loads(options)
        if not isinstance(opts,dict):raise ValueError()
        opts={k:v for k,v in opts.items() if k in ('size','voice','speed','seconds','aspect_ratio','resolution')}
        if len(str(opts))>500:raise ValueError()
        if any(not isinstance(opts.get(k,''),str) or len(opts.get(k,''))>12 for k in ('aspect_ratio','resolution')):raise ValueError()
        if 'speed' in opts and not .25<=float(opts['speed'])<=4:raise ValueError()
        if 'seconds' in opts and not 1<=int(opts['seconds'])<=60:raise ValueError()
    except (ValueError,TypeError):raise HTTPException(422,'ตัวเลือกสื่อไม่ถูกต้อง')
    if kind in ('image','video'):
        from .media import check_limits
        try:check_limits(opts,model.media_limits)
        except ValueError:raise HTTPException(422,'ตัวเลือกนี้ผู้ดูแลระบบไม่อนุญาตสำหรับโมเดลนี้ กรุณาเลือกจากรายการที่แสดง')
    if kind=='video' and not file and model.provider=='OpenRouter':
        import httpx
        from .media import model_options
        url,_=gateway.configuration(db,model.provider)
        if url:
            with httpx.Client(timeout=15,follow_redirects=False) as c:needs=model_options(c,url,model.provider,'video',model.api_id).get('requires_image')
            if needs:raise HTTPException(422,'โมเดลนี้สร้างวิดีโอจากภาพ กรุณาแนบภาพเฟรมแรก')
    j=GenerationJob(tenant_id=u.tenant_id,user_id=u.id,model_id=model.id,kind=kind,prompt=prompt,options=opts,status='awaiting_approval' if needs_approval else 'queued');db.add(j);db.flush()
    if kind in ('image','video') and file:
        if model.provider!='OpenRouter':raise HTTPException(422,'โมเดลนี้ไม่รองรับภาพต้นฉบับ (ใช้ได้กับโมเดล OpenRouter)')
        name=(file.filename or '').replace('\\','/').split('/')[-1]
        if name.rsplit('.',1)[-1].lower() not in ('png','jpg','jpeg','webp'):raise HTTPException(415,'รองรับภาพ PNG, JPG, WEBP เท่านั้น')
        data=await file.read(10*1024*1024+1)
        if not data or len(data)>10*1024*1024:raise HTTPException(413,'ภาพต้นฉบับต้องไม่เกิน 10 MB')
        from .antivirus import scan
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(scan,data)
        j.input_key=f'{u.tenant_id}/media-input/{j.id}';j.input_name=name;storage.put(j.input_key,data)
    if kind=='stt':
        if not file:raise HTTPException(422,'กรุณาเลือกไฟล์เสียง')
        name=(file.filename or '').replace('\\','/').split('/')[-1]
        if name.rsplit('.',1)[-1].lower() not in ('mp3','mp4','m4a','wav','webm','ogg','flac'):raise HTTPException(415,'ชนิดไฟล์เสียงไม่รองรับ')
        data=await file.read(20*1024*1024+1)
        if not data or len(data)>20*1024*1024:raise HTTPException(413,'ไฟล์เสียงต้องไม่เกิน 20 MB')
        from .antivirus import scan
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(scan,data)
        j.input_key=f'{u.tenant_id}/media-input/{j.id}';j.input_name=name;storage.put(j.input_key,data)
    db.commit();log(db,u,'ส่งงานสร้างสื่อ',kind)
    if needs_approval:
        savings.check_budget_alerts(u.tenant_id,u.id);return public_job(j)
    from .jobs import schedule_media
    schedule_media(j.id,background)
    return public_job(j)

def owned_job(db,u,id):
    j=db.scalar(select(GenerationJob).where(GenerationJob.id==id,GenerationJob.tenant_id==u.tenant_id,GenerationJob.user_id==u.id))
    if not j:raise HTTPException(404)
    return j

@router.get('/media/jobs')
def media_jobs(kind:str|None=None,u:User=Depends(current_user),db:Session=Depends(db_session)):
    s=select(GenerationJob).where(GenerationJob.tenant_id==u.tenant_id,GenerationJob.user_id==u.id)
    if kind:s=s.where(GenerationJob.kind==kind)
    return [public_job(j) for j in db.scalars(s.order_by(GenerationJob.created_at.desc()).limit(50))]

@router.post('/media/{id}/cancel')
def cancel_media(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    j=owned_job(db,u,id)
    if j.status not in ('queued','retrying','processing'):raise HTTPException(409,'งานสิ้นสุดแล้ว')
    j.status='cancelled';j.updated_at=now();db.commit();return {'ok':True,'notice':'หยุดงานในระบบแล้ว ผู้ให้บริการอาจยังคิดค่าใช้จ่าย'}

@router.post('/media/{id}/retry')
def retry_media(id:str,background:BackgroundTasks,u:User=Depends(current_user),db:Session=Depends(db_session)):
    j=owned_job(db,u,id)
    if j.status!='failed':raise HTTPException(409,'ลองใหม่ได้เฉพาะงานที่ไม่สำเร็จ')
    j.status='retrying';j.error='';db.commit()
    from .jobs import schedule_media
    schedule_media(id,background,retry=True)
    return {'ok':True}

@router.get('/media/{id}/content')
def media_content(id:str,download:bool=False,u:User=Depends(current_user),db:Session=Depends(db_session)):
    j=owned_job(db,u,id)
    if j.status!='completed' or not j.output_key:raise HTTPException(404)
    ext={'image':'png','video':'mp4','tts':'mp3','stt':'txt'}[j.kind]
    return Response(storage.get(j.output_key),media_type=j.output_type,headers={'Content-Disposition':f'{"attachment" if download else "inline"}; filename="{j.kind}-{j.id}.{ext}"','Cache-Control':'private, no-store'})

class FeedbackInput(BaseModel):
    value:Literal['helpful','unhelpful']

@router.post('/messages/{id}/feedback')
def feedback(id:str,body:FeedbackInput,u:User=Depends(current_user),db:Session=Depends(db_session)):
    m=db.scalar(select(Message).join(Conversation,Message.conversation_id==Conversation.id).where(Message.id==id,Message.tenant_id==u.tenant_id,Conversation.user_id==u.id,Message.role=='assistant'))
    if not m:raise HTTPException(404)
    f=db.scalar(select(MessageFeedback).where(MessageFeedback.message_id==id))
    if not f:f=MessageFeedback(tenant_id=u.tenant_id,user_id=u.id,message_id=id,value=body.value);db.add(f)
    f.value=body.value;db.commit();return {'ok':True}

class ConversationInput(BaseModel):
    title:str=Field(min_length=1,max_length=100)

def owned_conversation(db,u,id):
    c=db.scalar(select(Conversation).where(Conversation.id==id,Conversation.user_id==u.id,Conversation.tenant_id==u.tenant_id))
    if not c:raise HTTPException(404)
    return c

@router.put('/conversations/{id}')
def rename_conversation(id:str,body:ConversationInput,u:User=Depends(current_user),db:Session=Depends(db_session)):
    c=owned_conversation(db,u,id);c.title=body.title;db.commit();return {'ok':True}

class PasswordInput(BaseModel):
    current_password:str=Field(min_length=1,max_length=200)
    new_password:str=Field(min_length=12,max_length=200)

@router.post('/account/password')
def change_password(body:PasswordInput,request:Request,u:User=Depends(current_user),db:Session=Depends(db_session)):
    if u.role=='USER':raise HTTPException(403,'ผู้ใช้ทั่วไปเปลี่ยนรหัสผ่านเองไม่ได้ กรุณาติดต่อผู้ดูแลแผนกหรือ Super Admin')
    if not passwords.verify(body.current_password,u.password_hash):raise HTTPException(400,'รหัสผ่านปัจจุบันไม่ถูกต้อง')
    u.password_hash=passwords.hash(body.new_password)
    current=hashlib.sha256(request.cookies.get('hub_session','').encode()).hexdigest()
    db.execute(delete(LoginSession).where(LoginSession.user_id==u.id,LoginSession.token_hash!=current));db.commit();log(db,u,'เปลี่ยนรหัสผ่าน');return {'ok':True}

class KBEdit(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    name_en:str|None=Field(default=None,max_length=100)  # None = leave as it is
    description:str=Field(default='',max_length=500)
    department_id:str|None=Field(default=None,max_length=36)  # only a Super Admin may move a knowledge base to another department
    multimodal:bool|None=None  # None = leave as it is

@router.put('/knowledge-bases/{id}')
def edit_kb(id:str,body:KBEdit,u:User=Depends(current_user),db:Session=Depends(db_session)):
    manager(u);require_kb(db,u,id,True);kb=db.get(KnowledgeBase,id)
    if body.department_id is not None and body.department_id!=kb.department_id:
        if not privileged(u):raise HTTPException(403,'ย้ายคลังความรู้ไปแผนกอื่นได้เฉพาะ Super Admin')
        if body.department_id and not db.scalar(select(Group.id).where(Group.id==body.department_id,Group.tenant_id==u.tenant_id,Group.kind=='department')):raise HTTPException(422,'ไม่พบแผนกนี้ในองค์กร')
        kb.department_id=body.department_id
    if body.multimodal is not None:kb.multimodal=body.multimodal
    if body.name_en is not None:kb.name_en=body.name_en.strip()
    kb.name=body.name;kb.description=body.description;db.commit();log(db,u,'แก้ไขคลังความรู้',kb.name);return {'ok':True}

@router.post('/knowledge-bases/{id}/multimodal/apply')
def apply_multimodal(id:str,background:BackgroundTasks,u:User=Depends(current_user),db:Session=Depends(db_session)):
    """Re-index only the documents whose picture chunks must change: with the switch on, files that contain pictures and have none indexed yet;
    with it off, files that still hold picture chunks (so they are removed). Everything else is left alone."""
    manager(u);require_kb(db,u,id,True);kb=db.get(KnowledgeBase,id)
    from . import multimodal
    from .retrieval import Chunk
    if kb.multimodal and not multimodal.enabled():raise HTTPException(409,'ยังไม่ได้เปิด Multimodal RAG ของระบบ (MULTIMODAL_RAG) หรือยังไม่ได้ตั้งค่า API key ของ Google AI')
    have=set(db.scalars(select(Chunk.document_id).where(Chunk.tenant_id==u.tenant_id,Chunk.kind=='image')))
    docs=[d for d in db.scalars(select(Document).where(Document.tenant_id==u.tenant_id,Document.knowledge_base_id==id,~Document.id.in_(deleted_ids())))]
    todo=[]
    for d in docs:
        if kb.multimodal:
            if d.id in have:continue
            try:
                if multimodal.contains_pictures(d.name,storage.get(d.storage_key)):todo.append(d)
            except Exception:continue
        elif d.id in have:todo.append(d)
    from .jobs import schedule_ingest
    for d in todo:d.status='processing'
    db.commit()
    for d in todo:schedule_ingest(d.id,background,retry=True)  # a finished task must run again, as the Re-index button does
    log(db,u,'อัปเดตภาพในคลังความรู้',f'{kb.name}: {len(todo)} เอกสาร')
    return {'multimodal':kb.multimodal,'documents':len(docs),'reindexed':len(todo)}
