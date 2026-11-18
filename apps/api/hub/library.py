"""Putting a validated file into a knowledge base. One path for the upload route and for files the Agent saves."""
import hashlib,secrets
from fastapi import HTTPException
from sqlalchemy import select
from . import storage
from .models import Document,KnowledgeBase,Audit
from .feature_models import DocumentState
from .policies import require_kb

def add(db,u,kb_id,name,data,schedule):
    """Store `data` as a new document of the knowledge base `kb_id` (the caller must be allowed to write there) and call
    schedule(document id) to start indexing. A file already in the organisation is not stored twice.
    Returns (document id, duplicate, status)."""
    kb=db.scalar(select(KnowledgeBase).where(KnowledgeBase.id==kb_id,KnowledgeBase.tenant_id==u.tenant_id))
    if not kb: raise HTTPException(404,'ไม่พบคลังความรู้')
    require_kb(db,u,kb.id,True)
    digest=hashlib.sha256(data).hexdigest()
    existing=db.scalar(select(Document).where(Document.tenant_id==u.tenant_id,Document.sha256==digest))
    if existing:
        require_kb(db,u,existing.knowledge_base_id)
        if db.scalar(select(DocumentState).where(DocumentState.document_id==existing.id,DocumentState.deleted_at!='')): raise HTTPException(409,'ไฟล์นี้อยู่ในถังขยะ กรุณากู้คืนก่อน')
        return existing.id,True,existing.status
    key=f'{u.tenant_id}/{secrets.token_hex(16)}'; storage.put(key,data)
    d=Document(tenant_id=u.tenant_id,knowledge_base_id=kb.id,name=name,sha256=digest,size=len(data),storage_key=key)
    db.add(d); db.commit()
    db.add(Audit(tenant_id=u.tenant_id,user_id=u.id,actor=u.name,action='อัปโหลดเอกสาร',detail=d.name[:100]));db.commit()
    schedule(d.id)
    return d.id,False,d.status
