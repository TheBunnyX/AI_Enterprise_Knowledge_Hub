import asyncio, csv, hashlib, io, json, os, secrets, time
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session
from .database import db_session, SessionLocal
from .models import *
from .auth import current_user, admin, manager, issue_session, public_user, passwords, is_online, PRODUCTION
from .schemas import *
from .retrieval import search, ingest
from . import storage, gateway
from .uploads import read_validated
from .ops_models import Group
from .policies import department_ids, privileged, require_kb, visible_kbs, deleted_ids, available_models, require_document, visible_documents
from .feature_models import DocumentState, ModelPolicy, DocumentVersion

router=APIRouter(prefix='/api')
def serialize(obj, fields): return {f:getattr(obj,f) for f in fields.split()}
def audit(db,u,action,detail=''):
    db.add(Audit(tenant_id=u.tenant_id,user_id=u.id,actor=u.name,action=action,detail=detail)); db.commit()
def tenant_doc(db,u,id):
    d=db.scalar(select(Document).where(Document.id==id,Document.tenant_id==u.tenant_id))
    if not d or db.scalar(select(DocumentState).where(DocumentState.document_id==id,DocumentState.deleted_at!='')): raise HTTPException(404,'ไม่พบเอกสาร')
    require_document(db,u,id)
    return d

@router.get('/config')
def config():
    # One-click demo sign-in publishes passwords to anyone who can reach the server, so it never exists in production.
    demo=os.getenv('DEMO_ACCOUNTS','') if os.getenv('APP_ENV')!='production' else ''
    return {'demo_accounts':[dict(zip(('label','email','password'),a.split('|'))) for a in demo.split(';') if a.count('|')==2],'authentication':'Local session','ai_gateway_configured':gateway.configured()}

LOGIN_MAX_FAILS=int(os.getenv('LOGIN_MAX_FAILS','8'));LOGIN_WINDOW=int(os.getenv('LOGIN_LOCK_SECONDS','900'))
@router.post('/auth/login')
def login(body:Login,response:Response,db:Session=Depends(db_session)):
    from .clientip import current_ip
    lock_keys=[f'hub:loginfail:e:{body.email.lower()[:120]}',f'hub:loginfail:i:{current_ip.get() or "-"}']
    try:
        from .jobs import redis_client
        _r=redis_client()
        if any(int(_r.get(k) or 0)>=LOGIN_MAX_FAILS*(1 if i==0 else 5) for i,k in enumerate(lock_keys)): raise HTTPException(429,'ลองเข้าสู่ระบบผิดหลายครั้งเกินไป กรุณารอสักครู่แล้วลองใหม่',headers={'Retry-After':str(LOGIN_WINDOW)})
    except HTTPException: raise
    except Exception: _r=None
    u=db.scalar(select(User).where(User.email==body.email.lower()))
    if not u or not passwords.verify(body.password,u.password_hash) or not u.active:
        if _r:
            try:
                for k in lock_keys:
                    _r.incr(k); _r.expire(k,LOGIN_WINDOW)
            except Exception: pass
        raise HTTPException(401,'อีเมลหรือรหัสผ่านไม่ถูกต้อง')
    org=db.get(Organization,u.tenant_id)
    if org.status!='active': raise HTTPException(403,'องค์กรถูกระงับ')
    if _r:
        try:_r.delete(lock_keys[0])
        except Exception:pass
    issue_session(db,u,response); return public_user(u)

@router.post('/auth/logout')
def logout(request:Request,response:Response,db:Session=Depends(db_session)):
    h=hashlib.sha256(request.cookies.get('hub_session','').encode()).hexdigest()
    db.execute(delete(LoginSession).where(LoginSession.token_hash==h)); db.commit(); response.delete_cookie('hub_session'); return {'ok':True}

@router.get('/auth/me')
def me(u:User=Depends(current_user)): return public_user(u)

@router.get('/me/quota')
def my_quota(u:User=Depends(current_user),db:Session=Depends(db_session)):
    from .policies import user_spend
    # month_spend keeps its name for older clients; it is the spend in the current budget_period
    return {'monthly_budget':u.monthly_budget,'budget_period':u.budget_period or 'month','month_spend':user_spend(db,u)}

@router.get('/knowledge-bases')
def kbs(u:User=Depends(current_user),db:Session=Depends(db_session)):
    bases=db.scalars(select(KnowledgeBase).where(KnowledgeBase.tenant_id==u.tenant_id,KnowledgeBase.id.in_(visible_kbs(db,u)))).all()
    readable=set(visible_documents(db,u))  # resolved once for the whole list, not once per knowledge base
    counts={}
    for id,kb in db.execute(select(Document.id,Document.knowledge_base_id).where(Document.tenant_id==u.tenant_id)):
        if id in readable:counts[kb]=counts.get(kb,0)+1
    writable=set(visible_kbs(db,u,True));names=dict(db.execute(select(Group.id,Group.name).where(Group.tenant_id==u.tenant_id,Group.kind=='department')).all());names_en=dict(db.execute(select(Group.id,Group.name_en).where(Group.tenant_id==u.tenant_id,Group.kind=='department')).all())
    return [{**serialize(b,'id name name_en description department_id multimodal'),'department':names.get(b.department_id,''),'department_en':names_en.get(b.department_id,''),'can_write':b.id in writable,'documents':counts.get(b.id,0)} for b in bases]

def owner_department(db,u,wanted):
    """The department a new knowledge base belongs to: a Super Admin picks any real one (or none); a department admin's own."""
    mine=department_ids(db,u)
    if wanted:
        if not db.scalar(select(Group.id).where(Group.id==wanted,Group.tenant_id==u.tenant_id,Group.kind=='department')):raise HTTPException(422,'ไม่พบแผนกนี้ในองค์กร')
        if not privileged(u) and wanted not in mine:raise HTTPException(403,'สร้างคลังความรู้ได้เฉพาะแผนกที่คุณดูแล')
        return wanted
    if privileged(u) or not mine:return ''
    if len(mine)>1:raise HTTPException(422,'คุณดูแลหลายแผนก กรุณาเลือกแผนกของคลังความรู้')
    return next(iter(mine))

@router.post('/knowledge-bases',status_code=201)
def create_kb(body:KBCreate,u:User=Depends(current_user),db:Session=Depends(db_session)):
    manager(u)
    b=KnowledgeBase(tenant_id=u.tenant_id,name=body.name,name_en=body.name_en.strip(),description=body.description,multimodal=body.multimodal,department_id=owner_department(db,u,body.department_id))
    db.add(b); db.commit(); audit(db,u,'สร้างคลังความรู้',b.name); return serialize(b,'id name name_en description department_id multimodal')

@router.get('/documents')
def documents(u:User=Depends(current_user),db:Session=Depends(db_session)):
    readable=set(visible_documents(db,u));writable=set(visible_documents(db,u,True))  # resolved once, not once per row
    rows=db.scalars(select(Document).where(Document.tenant_id==u.tenant_id,~Document.id.in_(deleted_ids())).order_by(Document.created_at.desc()))
    return [{**serialize(d,'id name name_en knowledge_base_id size status error version created_at'),'can_write':d.id in writable} for d in rows if d.id in readable]

@router.post('/documents',status_code=201)
async def upload(background:BackgroundTasks,file:UploadFile=File(...),knowledge_base_id:str=Form(...),u:User=Depends(current_user),db:Session=Depends(db_session)):
    from . import library
    from .jobs import schedule_ingest
    kb=db.scalar(select(KnowledgeBase).where(KnowledgeBase.id==knowledge_base_id,KnowledgeBase.tenant_id==u.tenant_id))
    if not kb: raise HTTPException(404,'ไม่พบคลังความรู้')
    require_kb(db,u,kb.id,True)  # before the file is read, so a refused upload costs nothing
    name,data=await read_validated(file)
    id,duplicate,status=library.add(db,u,kb.id,name,data,lambda id:schedule_ingest(id,background))
    return {'id':id,'duplicate':True,'status':status} if duplicate else {'id':id,'status':status}

@router.get('/documents/{id}')
def preview(id:str,version:int|None=None,u:User=Depends(current_user),db:Session=Depends(db_session)):
    d=tenant_doc(db,u,id)
    if version is not None and version!=d.version:
        old=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==id,DocumentVersion.tenant_id==u.tenant_id,DocumentVersion.version==version))
        if not old:raise HTTPException(404,'ไม่พบเวอร์ชันเอกสาร')
        from .retrieval import parse
        pages=parse(old.name,storage.get(old.storage_key))
        return {'id':id,'name':old.name,'status':'ready','error':'','version':version,'download_url':f'/api/documents/{id}/versions/{old.id}/download','pages':[{'id':str(i),'page':page,'text':text} for i,(page,text) in enumerate(pages)]}
    chunks=db.scalars(select(Chunk).where(Chunk.document_id==d.id,Chunk.tenant_id==u.tenant_id).order_by(Chunk.page,Chunk.created_at)).all()
    return {**serialize(d,'id name status error version'),'download_url':f'/api/documents/{id}/download','pages':[serialize(c,'id page text') for c in chunks]}

@router.get('/documents/{id}/download')
def download(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    from urllib.parse import quote
    d=tenant_doc(db,u,id); audit(db,u,'ดาวน์โหลดเอกสาร',d.name)
    return Response(storage.get(d.storage_key),media_type='application/octet-stream',headers={'Content-Disposition':f"attachment; filename*=UTF-8''{quote(d.name)}"})

@router.post('/documents/{id}/reindex')
def reindex(id:str,background:BackgroundTasks,u:User=Depends(current_user),db:Session=Depends(db_session)):
    manager(u); d=tenant_doc(db,u,id); require_document(db,u,id,True); d.status='processing'; db.commit(); from .jobs import schedule_ingest; schedule_ingest(d.id,background,retry=True); audit(db,u,'จัดทำดัชนีใหม่',d.name); return {'ok':True}

@router.put('/documents/{id}/names')
def rename_document(id:str,body:DocumentNames,u:User=Depends(current_user),db:Session=Depends(db_session)):
    """Edit the file name and/or the English name. The extension of the file name is fixed: it decides how the file is read and downloaded."""
    manager(u); d=tenant_doc(db,u,id); require_document(db,u,id,True)
    if body.name is not None:
        name=' '.join(body.name.replace('\\','/').split('/')[-1].split())
        if not name: raise HTTPException(422,'ชื่อไฟล์ต้องไม่ว่าง')
        old_ext=d.name.rsplit('.',1)[-1].lower() if '.' in d.name else ''; new_ext=name.rsplit('.',1)[-1].lower() if '.' in name else ''
        if new_ext!=old_ext: raise HTTPException(422,'ต้องคงนามสกุลไฟล์เดิมไว้ (.'+old_ext+')' if old_ext else 'ชื่อไฟล์ต้องไม่มีนามสกุล')
        d.name=name
    if body.name_en is not None: d.name_en=' '.join(body.name_en.split())
    db.commit(); audit(db,u,'แก้ไขชื่อเอกสาร',d.name[:100])
    return {'id':d.id,'name':d.name,'name_en':d.name_en}

@router.delete('/documents/{id}')
def delete_doc(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    manager(u); d=tenant_doc(db,u,id); require_document(db,u,id,True)
    if os.getenv('QDRANT_URL'):
        from qdrant_client import QdrantClient, models
        from .retrieval import COLLECTION
        QdrantClient(url=os.environ['QDRANT_URL']).delete(COLLECTION,models.FilterSelector(filter=models.Filter(must=[models.FieldCondition(key='tenant_id',match=models.MatchValue(value=u.tenant_id)),models.FieldCondition(key='document_id',match=models.MatchValue(value=d.id))])),wait=True)
    db.execute(delete(Chunk).where(Chunk.document_id==id,Chunk.tenant_id==u.tenant_id))
    state=db.scalar(select(DocumentState).where(DocumentState.document_id==id))
    if not state: state=DocumentState(tenant_id=u.tenant_id,document_id=id);db.add(state)
    state.deleted_at=now();db.commit();audit(db,u,'ย้ายเอกสารไปถังขยะ',d.name);return {'ok':True}

@router.get('/search')
def knowledge_search(q:str=Query(min_length=1,max_length=2000),kb_id:str|None=None,mode:str=Query('hybrid',pattern='^(hybrid|keyword|semantic)$'),limit:int=Query(int(os.getenv('SEARCH_CANDIDATES','20')),ge=1,le=50),per_doc:int=Query(int(os.getenv('SEARCH_PER_DOC','3')),ge=1,le=10),u:User=Depends(current_user),db:Session=Depends(db_session)):
    """The search page. The reranker is a CPU cross-encoder, so it only judges the best `limit` candidates (50 took about 12 s, 15 takes a few seconds),
    and a passage the reranker finds barely related (below SEARCH_MIN_SCORE) is left out of the list."""
    floor=float(os.getenv('SEARCH_MIN_SCORE','0.03'))
    strict=search(db,u.tenant_id,q,kb_id,mode=mode,limit=limit,user=u,per_doc=per_doc)
    found=[r for r in strict if r.get('rerank_score',1)>=floor]
    if found:return found
    # Nothing is clearly relevant (a question in another language scores low against Thai passages): keep the weaker strict
    # candidates, flagged as approximate. They already passed the lexical/semantic thresholds, so they are not noise.
    fallback=float(os.getenv('SEARCH_FALLBACK_MIN','0.005'))
    weak=[r|{'approx':True} for r in strict if r.get('rerank_score',1)>=fallback]
    if weak:return weak[:5]
    # Still nothing (typo): retry loosely and let the reranker judge.
    return [r|{'approx':True} for r in search(db,u.tenant_id,q,kb_id,mode=mode,limit=8,user=u,relaxed=True,per_doc=2,pool=8) if r.get('rerank_score',1)>=fallback][:5]

@router.get('/chunks/{id}/image')
def chunk_image(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    """The picture behind a picture chunk (a figure of a document), for the thumbnails in search results. Same access rule as the document."""
    c=db.scalar(select(Chunk).where(Chunk.id==id,Chunk.tenant_id==u.tenant_id,Chunk.kind=='image'))
    if not c or not c.image_key:raise HTTPException(404,'ไม่พบภาพ')
    require_document(db,u,c.document_id)
    try:data=storage.get(c.image_key)
    except Exception:raise HTTPException(404,'ไม่พบภาพ')
    return Response(content=data,media_type='image/jpeg',headers={'Cache-Control':'private, max-age=3600','Content-Disposition':'inline'})

@router.get('/conversations')
def conversations(u:User=Depends(current_user),db:Session=Depends(db_session)):
    return [serialize(c,'id title created_at') for c in db.scalars(select(Conversation).where(Conversation.tenant_id==u.tenant_id,Conversation.user_id==u.id).order_by(Conversation.created_at.desc()))]

def _delete_conversations(db,u,ids):
    """Permanently delete the user's own conversations with messages, feedback and share links. Usage/cost records are kept for billing."""
    from .feature_models import MessageFeedback
    from .ops_models import ConversationShare
    if not ids:return 0
    mids=select(Message.id).where(Message.conversation_id.in_(ids),Message.tenant_id==u.tenant_id)
    db.execute(delete(MessageFeedback).where(MessageFeedback.message_id.in_(mids)))
    db.execute(delete(ConversationShare).where(ConversationShare.conversation_id.in_(ids),ConversationShare.tenant_id==u.tenant_id))
    db.execute(delete(Message).where(Message.conversation_id.in_(ids),Message.tenant_id==u.tenant_id))
    db.execute(delete(Conversation).where(Conversation.id.in_(ids),Conversation.tenant_id==u.tenant_id,Conversation.user_id==u.id))
    db.commit();return len(ids)

@router.delete('/conversations/{id}')
def delete_conversation(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    c=db.scalar(select(Conversation).where(Conversation.id==id,Conversation.tenant_id==u.tenant_id,Conversation.user_id==u.id))
    if not c: raise HTTPException(404,'ไม่พบบทสนทนา')
    title=c.title;_delete_conversations(db,u,[id]);audit(db,u,'ลบบทสนทนา',title[:100]);return {'ok':True}

class ConversationIds(BaseModel):
    ids:list[str]=Field(min_length=1,max_length=200)

@router.post('/conversations/delete')
def delete_some_conversations(body:ConversationIds,u:User=Depends(current_user),db:Session=Depends(db_session)):
    ids=list(db.scalars(select(Conversation.id).where(Conversation.id.in_(body.ids),Conversation.tenant_id==u.tenant_id,Conversation.user_id==u.id)))  # only the caller's own
    n=_delete_conversations(db,u,ids);audit(db,u,'ลบบทสนทนาที่เลือก',str(n)+' บทสนทนา');return {'ok':True,'deleted':n}

@router.delete('/conversations')
def delete_all_conversations(u:User=Depends(current_user),db:Session=Depends(db_session)):
    ids=list(db.scalars(select(Conversation.id).where(Conversation.tenant_id==u.tenant_id,Conversation.user_id==u.id)))
    n=_delete_conversations(db,u,ids);audit(db,u,'ลบประวัติสนทนาทั้งหมด',str(n)+' บทสนทนา');return {'ok':True,'deleted':n}

@router.get('/conversations/{id}')
def messages(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    c=db.scalar(select(Conversation).where(Conversation.id==id,Conversation.tenant_id==u.tenant_id,Conversation.user_id==u.id))
    if not c: raise HTTPException(404)
    return [serialize(m,'id role content citations created_at') for m in db.scalars(select(Message).where(Message.conversation_id==id,Message.tenant_id==u.tenant_id).order_by(Message.created_at))]

@router.get('/conversations/{id}/agent-pending')
def agent_pending(id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    """What an agent run of this conversation is waiting for from its user (a question or an approval), or null."""
    from . import agent_store
    if not db.scalar(select(Conversation.id).where(Conversation.id==id,Conversation.tenant_id==u.tenant_id,Conversation.user_id==u.id)): raise HTTPException(404,'ไม่พบบทสนทนา')
    run=agent_store.waiting(db,u,id)
    return run.pending if run else None

@router.post('/chat')
async def chat(body:ChatInput,request:Request,u:User=Depends(current_user),db:Session=Depends(db_session)):
    from .chat_service import chat_response
    return await chat_response(body,request,u,db)

@router.post('/chat/attachments',status_code=201)
async def chat_attachment(file:UploadFile=File(...),u:User=Depends(current_user)):
    """Temporary file for one question: text is extracted and kept per user, never indexed or shared."""
    from starlette.concurrency import run_in_threadpool
    from .retrieval import parse
    from .chat_service import ATTACH_STORE_CHARS, attachment_key
    name,data=await read_validated(file)
    try:pages=await run_in_threadpool(parse,name,data)
    except HTTPException:raise
    except Exception:raise HTTPException(422,'อ่านไฟล์ไม่สำเร็จ')
    text=chr(10).join(t.strip() for _,t in pages if t and t.strip())
    if not text:raise HTTPException(422,'ไม่พบข้อความในไฟล์')
    id=secrets.token_hex(16)
    storage.put(attachment_key(u,id),json.dumps({'name':name,'text':text[:ATTACH_STORE_CHARS]},ensure_ascii=False).encode())
    return {'id':id,'name':name,'chars':len(text),'truncated':len(text)>ATTACH_STORE_CHARS}

def rate_usage():
    """{(provider, model): (requests last minute, tokens last minute, requests today)} across all tenants (a provider key is shared). Google's daily quota resets at midnight Pacific time."""
    from zoneinfo import ZoneInfo
    now=datetime.now(timezone.utc);minute=(now-timedelta(seconds=60)).isoformat()
    def day_start(provider):
        try:tz=ZoneInfo('America/Los_Angeles') if provider=='Google AI' else timezone.utc
        except Exception:tz=timezone.utc
        return now.astimezone(tz).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).isoformat()
    out={}
    with SessionLocal() as s:  # system context: counts must not be limited to the caller's tenant
        for provider in {p for p in s.scalars(select(Usage.provider).distinct()) if p}:
            since=min(day_start(provider),minute)
            for model,created,tokens in s.execute(select(Usage.model,Usage.created_at,Usage.input_tokens+Usage.output_tokens).where(Usage.provider==provider,Usage.created_at>=since)):
                r,t,d=out.get((provider,model),(0,0,0))
                out[(provider,model)]=(r+(created>=minute),t+(tokens if created>=minute else 0),d+(created>=day_start(provider)))
    return out

@router.get('/models')
def model_list(u:User=Depends(current_user),db:Session=Depends(db_session)):
    stmt=select(AIModel)
    if u.role!='SUPER_ADMIN': stmt=stmt.where(AIModel.id.in_([m.id for m in available_models(db,u)]))
    counters=rate_usage()
    rows=list(db.scalars(stmt));shared={n for n in (m.name for m in rows) if sum(1 for x in rows if x.name==n)>1}
    return [{**serialize(m,'id name provider api_id category enabled input_price output_price effort media_limits'),'display_name':f'{m.name} {m.provider}' if m.name in shared else m.name,'rpm':m.rpm,'tpm':m.tpm,'rpd':m.rpd,**dict(zip(('used_rpm','used_tpm','used_rpd'),counters.get((m.provider,m.name),(0,0,0)))),'configured':gateway.configured(db,m.provider)} for m in rows]

@router.post('/admin/models',status_code=201)
def add_model(body:ModelInput,u:User=Depends(admin),db:Session=Depends(db_session)):
    from .policies import allow_new_model
    m=AIModel(**body.model_dump()); db.add(m); db.commit(); allow_new_model(db,m); audit(db,u,'เพิ่มโมเดล',m.name); return {'id':m.id}

@router.put('/admin/models/{id}')
def update_model(id:str,body:ModelInput,u:User=Depends(admin),db:Session=Depends(db_session)):
    m=db.get(AIModel,id)
    if not m: raise HTTPException(404)
    for k,v in body.model_dump().items(): setattr(m,k,v)
    db.commit(); audit(db,u,'แก้ไขโมเดล',m.name); return {'ok':True}

@router.get('/admin/organizations')
def organizations(u:User=Depends(admin),db:Session=Depends(db_session)):
    audit(db,u,'ดูรายการองค์กรทั้งหมด')
    return [{**serialize(o,'id name status quota created_at'),'users':db.scalar(select(func.count()).select_from(User).where(User.tenant_id==o.id)),'documents':db.scalar(select(func.count()).select_from(Document).where(Document.tenant_id==o.id)),'cost':db.scalar(select(func.coalesce(func.sum(Usage.cost),0)).where(Usage.tenant_id==o.id))} for o in db.scalars(select(Organization).order_by(Organization.created_at))]

@router.post('/admin/organizations',status_code=201)
def create_org(body:OrgInput,u:User=Depends(admin),db:Session=Depends(db_session)):
    o=Organization(**body.model_dump()); db.add(o); db.commit(); audit(db,u,'สร้างองค์กร',o.name); return {'id':o.id}

@router.put('/admin/organizations/{id}')
def update_org(id:str,body:OrgInput,u:User=Depends(admin),db:Session=Depends(db_session)):
    o=db.get(Organization,id)
    if not o: raise HTTPException(404)
    if o.id==u.tenant_id and body.status!='active': raise HTTPException(400,'ไม่สามารถระงับองค์กรที่กำลังใช้งานได้')
    for k,v in body.model_dump().items(): setattr(o,k,v)
    db.commit(); audit(db,u,'แก้ไของค์กร',o.name); return {'ok':True}

@router.get('/admin/users')
def users(u:User=Depends(admin),db:Session=Depends(db_session)):
    return [{**public_user(a),'active':a.active,'online':is_online(a)} for a in db.scalars(select(User))]

@router.post('/admin/users',status_code=201)
def create_user(body:UserInput,u:User=Depends(admin),db:Session=Depends(db_session)):
    if not db.get(Organization,body.tenant_id): raise HTTPException(404,'ไม่พบองค์กร')
    if db.scalar(select(User).where(User.email==body.email.lower())): raise HTTPException(409,'อีเมลนี้มีอยู่แล้ว')
    values=body.model_dump(exclude={'password','department_id'}); values['email']=body.email.lower()
    if body.role!='SUPER_ADMIN':
        if not body.department_id: raise HTTPException(422,'ผู้ใช้ทุกคนต้องอยู่ในฝ่าย กรุณาเลือกฝ่าย')
        from .ops_models import Group, GroupMember
        if not db.scalar(select(Group).where(Group.id==body.department_id,Group.tenant_id==body.tenant_id,Group.kind=='department')): raise HTTPException(422,'ไม่พบฝ่ายในองค์กรนี้')
    a=User(**values,password_hash=passwords.hash(body.password)); db.add(a); db.flush()
    if body.role!='SUPER_ADMIN': db.add(GroupMember(tenant_id=body.tenant_id,group_id=body.department_id,user_id=a.id))
    db.commit(); audit(db,u,'เพิ่มผู้ใช้',a.email); return public_user(a)

@router.post('/admin/users/{id}/toggle')
def toggle_user(id:str,u:User=Depends(admin),db:Session=Depends(db_session)):
    a=db.get(User,id)
    if not a: raise HTTPException(404)
    if a.id==u.id: raise HTTPException(400,'ไม่สามารถระงับบัญชีตนเอง')
    a.active=not a.active; db.execute(delete(LoginSession).where(LoginSession.user_id==a.id)); db.commit(); audit(db,u,'เปลี่ยนสถานะผู้ใช้',a.email); return {'active':a.active}

@router.get('/analytics')
def analytics(days:int=Query(30,ge=1,le=365),tenant_id:str|None=None,u:User=Depends(current_user),db:Session=Depends(db_session)):
    """Usage and cost by role (policies.spending_scope): a user sees their own, a department admin their department's, a
    Super Admin the organisation's. Document and knowledge-base counts follow what the caller may read."""
    from datetime import timedelta
    from .policies import spending_scope
    kind,people_ids=spending_scope(db,u);everything=people_ids is None
    tenant=tenant_id if everything else u.tenant_id
    def scope(stmt,cls): return stmt.where(cls.tenant_id==tenant) if tenant else stmt
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    used=scope(select(Usage).where(Usage.created_at>=cutoff),Usage)
    if not everything:used=used.where(Usage.user_id.in_(people_ids))
    events=db.scalars(used).all()
    today=datetime.now(timezone.utc).date()
    daily={(today-timedelta(days=i)).isoformat():{'date':(today-timedelta(days=i)).isoformat(),'requests':0,'cost':0,'input_tokens':0,'output_tokens':0} for i in range(min(days,365)-1,-1,-1)}
    models={}; people={}
    for e in events:
        day=daily.setdefault(e.created_at[:10],{'date':e.created_at[:10],'requests':0,'cost':0,'input_tokens':0,'output_tokens':0})
        day['requests']+=1; day['cost']+=e.cost; day['input_tokens']+=e.input_tokens; day['output_tokens']+=e.output_tokens
        for table,key in ((models,e.model),(people,e.user_id)):
            row=table.setdefault(key,{'requests':0,'input_tokens':0,'output_tokens':0,'cost':0}); row['requests']+=1; row['input_tokens']+=e.input_tokens; row['output_tokens']+=e.output_tokens; row['cost']+=e.cost
    names={x.id:x.name for x in db.scalars(select(User).where(User.id.in_(list(people))))} if people else {}
    def count(cls,*where): return db.scalar(scope(select(func.count()).select_from(cls).where(*where),cls))
    if everything:
        statuses=dict(db.execute(scope(select(Document.status,func.count()).where(~Document.id.in_(deleted_ids())).group_by(Document.status),Document)).all())
        totals={'organizations':db.scalar(select(func.count()).select_from(Organization)),'users':db.scalar(scope(select(func.count()).select_from(User),User)),
            'documents':db.scalar(scope(select(func.count()).select_from(Document).where(~Document.id.in_(deleted_ids())),Document)),'storage_bytes':db.scalar(scope(select(func.coalesce(func.sum(Document.size),0)),Document)),
            'knowledge_bases':count(KnowledgeBase),'conversations':count(Conversation),'messages':count(Message)}
    else:
        readable=set(visible_documents(db,u));statuses={};size=0;documents=0
        for id,status,bytes_ in db.execute(select(Document.id,Document.status,Document.size).where(Document.tenant_id==u.tenant_id)):
            if id in readable:documents+=1;size+=bytes_;statuses[status]=statuses.get(status,0)+1
        mine=select(Conversation.id).where(Conversation.tenant_id==u.tenant_id,Conversation.user_id==u.id)  # conversations are private to their owner
        totals={'organizations':1,'users':len(people_ids),'documents':documents,'storage_bytes':size,'knowledge_bases':len(visible_kbs(db,u)),
            'conversations':count(Conversation,Conversation.user_id==u.id),'messages':count(Message,Message.conversation_id.in_(mine))}
    return {**totals,'scope':kind,'requests':len(events),'cost':sum(e.cost for e in events),'input_tokens':sum(e.input_tokens for e in events),'output_tokens':sum(e.output_tokens for e in events),'daily':sorted(daily.values(),key=lambda d:d['date']),'models':[{'name':k,'value':v['requests']} for k,v in models.items()],
        'model_rows':sorted(({'name':k,**v} for k,v in models.items()),key=lambda r:-r['requests']),
        'top_users':sorted(({'name':names.get(k,'(ผู้ใช้ที่ถูกลบ)'),**v} for k,v in people.items()),key=lambda r:-r['requests'])[:10],
        'document_status':statuses,'days':days,'estimated':any(e.estimated for e in events)}

@router.get('/audit')
def audits(u:User=Depends(current_user),db:Session=Depends(db_session)):
    stmt=select(Audit)
    if u.role!='SUPER_ADMIN': stmt=stmt.where(Audit.tenant_id==u.tenant_id,Audit.user_id==u.id)
    return [serialize(a,'id actor action detail ip created_at') for a in db.scalars(stmt.order_by(Audit.created_at.desc()).limit(100))]

@router.get('/audit/export')
def export_audit(days:int=Query(30,ge=1,le=365),format:str=Query('csv',pattern='^(csv|json)$'),tenant_id:str|None=None,u:User=Depends(current_user),db:Session=Depends(db_session)):
    from datetime import timedelta
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    stmt=select(Audit).where(Audit.created_at>=cutoff)
    if u.role!='SUPER_ADMIN': stmt=stmt.where(Audit.tenant_id==u.tenant_id,Audit.user_id==u.id)
    elif tenant_id: stmt=stmt.where(Audit.tenant_id==tenant_id)
    rows=list(db.scalars(stmt.order_by(Audit.created_at.desc()).limit(50000)))
    audit(db,u,'ส่งออกบันทึกการใช้งาน',f'{format} · {days} วัน · {len(rows)} รายการ')
    if format=='json':
        return Response(json.dumps([serialize(a,'id tenant_id actor action detail ip created_at') for a in rows],ensure_ascii=False,default=str),media_type='application/json',headers={'Content-Disposition':'attachment; filename="audit-log.json"'})
    def safe(v):
        v='' if v is None else str(v)
        return "'"+v if v[:1] in ('=','+','-','@','\t','\r') else v
    out=io.StringIO(); w=csv.writer(out); w.writerow(['date','tenant_id','actor','action','detail','ip'])
    for a in rows: w.writerow([a.created_at,a.tenant_id,safe(a.actor),safe(a.action),safe(a.detail),safe(a.ip)])
    return Response('\ufeff'+out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="audit-log.csv"'})

@router.get('/usage/export')
def export(days:int=Query(30,ge=1,le=365),tenant_id:str|None=None,u:User=Depends(current_user),db:Session=Depends(db_session)):
    from datetime import timedelta
    from .policies import spending_scope
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    stmt=select(Usage).where(Usage.created_at>=cutoff)
    _,people_ids=spending_scope(db,u)  # the same people whose usage the caller sees in analytics
    if people_ids is not None: stmt=stmt.where(Usage.tenant_id==u.tenant_id,Usage.user_id.in_(people_ids))
    elif tenant_id: stmt=stmt.where(Usage.tenant_id==tenant_id)
    out=io.StringIO(); w=csv.writer(out); w.writerow(['date','tenant_id','model','input_tokens','output_tokens','cost_usd','estimated'])
    for e in db.scalars(stmt): w.writerow([e.created_at,e.tenant_id,"'"+e.model,e.input_tokens,e.output_tokens,e.cost,e.estimated])
    return Response('\ufeff'+out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="usage.csv"'})

@router.get('/health')
def health(): return {'status':'ok'}

@router.get('/system')
def system(u:User=Depends(admin),db:Session=Depends(db_session)):
    db.execute(select(1))
    return {'api':'healthy','database':'healthy','storage':'S3 / SeaweedFS configured' if os.getenv('S3_ENDPOINT') else 'local filesystem','vector':'Qdrant configured' if os.getenv('QDRANT_URL') else 'local CPU demo','queue':'Celery configured' if os.getenv('CELERY_BROKER_URL') else 'in-process background tasks','llm':'configured' if gateway.configured(db) else 'not configured','antivirus':'ClamAV configured' if os.getenv('CLAMAV_HOST') else 'not configured','backup':'encrypted snapshots configured' if os.getenv('SECRETS_KEY') or os.getenv('BACKUP_ENCRYPTION_KEY') else 'not configured'}

@router.get('/system/health')
def system_health(u:User=Depends(current_user)):
    """Up/down only (no hosts or errors), so every signed-in user can see the sidebar indicator."""
    from .infra_health import check
    return check()

@router.post('/studio/{kind}')
def studio(kind:str,u:User=Depends(current_user)):
    raise HTTPException(503,'ยังไม่ได้เชื่อมต่อผู้ให้บริการ '+kind+' กรุณาตั้งค่า provider adapter ก่อนใช้งาน')
