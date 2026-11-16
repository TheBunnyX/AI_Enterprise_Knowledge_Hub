"""Sources a department's knowledge base syncs from. Managed by whoever may write to the knowledge base, nobody else."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import current_user, manager
from .database import db_session
from .models import Audit, KnowledgeBase, User
from .policies import require_kb
from .sync_models import KBSource
from . import sync

router = APIRouter(prefix='/api/knowledge-bases/{kb}/sources')


class SourceInput(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    interval_minutes: int = Field(default=1440, ge=sync.MIN_INTERVAL, le=60 * 24 * 30)
    enabled: bool = True


def public(s): return {f: getattr(s, f) for f in 'id url interval_minutes enabled document_id last_checked last_status last_error'.split()}


def writable_kb(db, u, kb):
    manager(u); require_kb(db, u, kb, True)
    if not db.scalar(select(KnowledgeBase.id).where(KnowledgeBase.id == kb, KnowledgeBase.tenant_id == u.tenant_id)): raise HTTPException(404, 'ไม่พบคลังความรู้')


def source_of(db, u, kb, id):
    s = db.scalar(select(KBSource).where(KBSource.id == id, KBSource.knowledge_base_id == kb, KBSource.tenant_id == u.tenant_id))
    if not s: raise HTTPException(404, 'ไม่พบแหล่งข้อมูล')
    return s


def audit(db, u, action, detail): db.add(Audit(tenant_id=u.tenant_id, user_id=u.id, actor=u.name, action=action, detail=detail)); db.commit()


@router.get('')
def list_sources(kb: str, u: User = Depends(current_user), db: Session = Depends(db_session)):
    writable_kb(db, u, kb)
    return [public(s) for s in db.scalars(select(KBSource).where(KBSource.knowledge_base_id == kb, KBSource.tenant_id == u.tenant_id).order_by(KBSource.created_at))]


@router.post('', status_code=201)
def add_source(kb: str, body: SourceInput, u: User = Depends(current_user), db: Session = Depends(db_session)):
    writable_kb(db, u, kb)
    try: sync.check_url(body.url)
    except ValueError as e: raise HTTPException(422, str(e))
    s = KBSource(tenant_id=u.tenant_id, knowledge_base_id=kb, url=body.url.strip(), interval_minutes=body.interval_minutes, enabled=body.enabled)
    db.add(s); db.commit(); audit(db, u, 'เพิ่มแหล่งซิงก์', s.url); return public(s)


@router.delete('/{id}')
def remove_source(kb: str, id: str, u: User = Depends(current_user), db: Session = Depends(db_session)):
    writable_kb(db, u, kb); s = source_of(db, u, kb, id); url = s.url
    db.delete(s); db.commit(); audit(db, u, 'ลบแหล่งซิงก์', url); return {'ok': True}  # the documents it created stay


@router.post('/{id}/sync')
def sync_now(kb: str, id: str, u: User = Depends(current_user), db: Session = Depends(db_session)):
    writable_kb(db, u, kb); source_of(db, u, kb, id)
    status = sync.sync_source(id); db.expire_all()
    s = source_of(db, u, kb, id)
    return {'status': status, **public(s)}
