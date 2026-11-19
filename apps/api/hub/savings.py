"""Cost controls: answer and embedding caches, model routing, prompt caching, limits, alerts and the savings report."""
import hashlib, json, re
from datetime import datetime, timedelta, timezone
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import db_session, SessionLocal
from .models import User, Usage, Audit, Organization, AIModel
from .feature_models import Setting, GenerationJob, ModelPolicy
from .ops_models import Group, GroupMember
from .auth import current_user, admin
from .savings_models import AnswerCache, EmbeddingCache, SavingsEvent
from . import gateway, alerts

router = APIRouter(prefix='/api')

DEFAULTS = {
    'cache': True, 'cache_days': 7,
    'auto_route': False, 'router_model': 'respan/span-01-lite:free',
    'history_messages': 2, 'history_chars': 1500, 'max_output_tokens': 1024,
    'rate_per_minute': 20, 'daily_requests': 0, 'alert_percent': 80,
    'media_daily_limit': 10, 'media_approval_usd': 0.0, 'media_daily_usd': 0.0,
    'web_search': 'ask',  # off = never; ask = the user switches it on, or approves each search an agent asks for; always = agents search without asking
}

class PolicyInput(BaseModel):
    cache: bool = True
    cache_days: int = Field(default=7, ge=1, le=90)
    auto_route: bool = False
    router_model: str = Field(default='respan/span-01-lite:free', min_length=1, max_length=200)
    history_messages: int = Field(default=2, ge=0, le=20)
    history_chars: int = Field(default=1500, ge=200, le=8000)
    max_output_tokens: int = Field(default=1024, ge=128, le=8192)
    rate_per_minute: int = Field(default=20, ge=0, le=1000)
    daily_requests: int = Field(default=0, ge=0, le=100000)
    alert_percent: int = Field(default=80, ge=1, le=100)
    media_daily_limit: int = Field(default=10, ge=0, le=1000)
    media_approval_usd: float = Field(default=0, ge=0, le=100000)
    media_daily_usd: float = Field(default=0, ge=0, le=100000)
    web_search: Literal['off', 'ask', 'always'] = 'ask'

def utc_now(): return datetime.now(timezone.utc)

def policy(db, tenant_id):
    s = db.scalar(select(Setting).where(Setting.key == 'savings:' + tenant_id))
    return DEFAULTS | (s.value if s else {})

def log(db, u, action, detail=''):
    db.add(Audit(tenant_id=u.tenant_id, user_id=u.id, actor=u.name, action=action, detail=detail)); db.commit()

@router.get('/savings/status')
def status(u: User = Depends(current_user), db: Session = Depends(db_session)):
    p = policy(db, u.tenant_id)
    return {k: p[k] for k in ('auto_route', 'media_daily_limit', 'media_approval_usd', 'media_daily_usd', 'web_search')}

@router.get('/savings/policy')
def get_policy(u: User = Depends(admin), db: Session = Depends(db_session)):
    return policy(db, u.tenant_id)

@router.put('/savings/policy')
def save_policy(body: PolicyInput, u: User = Depends(admin), db: Session = Depends(db_session)):
    s = db.scalar(select(Setting).where(Setting.key == 'savings:' + u.tenant_id))
    if not s: s = Setting(key='savings:' + u.tenant_id, value={}); db.add(s)
    s.value = body.model_dump()
    db.commit(); log(db, u, 'เปลี่ยนการตั้งค่าการประหยัดค่าใช้จ่าย')
    return policy(db, u.tenant_id)

# ---------- answer cache ----------
def normalize(question): return re.sub(r'\s+', ' ', question.strip().lower())

def answer_key(tenant_id, question, chunk_ids, max_tokens):
    """Same question over the same evidence this user may see, so permissions and document changes invalidate it."""
    return hashlib.sha256(json.dumps([tenant_id, normalize(question), list(chunk_ids), max_tokens], ensure_ascii=False).encode()).hexdigest()

def cache_lookup(db, key):
    e = db.scalar(select(AnswerCache).where(AnswerCache.cache_key == key))
    return e if e and e.expires_at > utc_now().isoformat() else None

def record_event(tenant_id, user_id, kind, saved=0.0, detail=''):
    with SessionLocal() as db:
        db.add(SavingsEvent(tenant_id=tenant_id, user_id=user_id, kind=kind, saved=saved, detail=detail[:200])); db.commit()

def register_hit(entry_id, tenant_id, user_id, saved):
    with SessionLocal() as db:
        e = db.get(AnswerCache, entry_id)
        if e: e.hits += 1
        db.add(SavingsEvent(tenant_id=tenant_id, user_id=user_id, kind='cache_hit', saved=saved, detail=(e.model if e else ''))); db.commit()

def cache_store(tenant_id, key, question, answer, citations, model, cost, days):
    with SessionLocal() as db:
        purge_expired(db)
        e = db.scalar(select(AnswerCache).where(AnswerCache.cache_key == key))
        if not e: e = AnswerCache(tenant_id=tenant_id, cache_key=key); db.add(e)
        e.question = question[:500]; e.answer = answer; e.citations = citations; e.model = model; e.cost = cost
        e.expires_at = (utc_now() + timedelta(days=days)).isoformat()
        try: db.commit()
        except IntegrityError: db.rollback()

def purge_expired(db):
    db.execute(AnswerCache.__table__.delete().where(AnswerCache.expires_at < utc_now().isoformat())); db.commit()

# ---------- embedding cache ----------
def embedding_key(version, tenant_id, text):
    return hashlib.sha256((version + '|' + tenant_id + '|' + text).encode()).hexdigest()

def cached_vectors(keys, dimensions):
    if not keys: return {}
    with SessionLocal() as db:
        rows = db.execute(select(EmbeddingCache.cache_key, EmbeddingCache.vector).where(EmbeddingCache.cache_key.in_(keys)))
        return {k: v for k, v in rows if isinstance(v, list) and len(v) == dimensions}

def store_vectors(pairs):
    if not pairs: return
    with SessionLocal() as db:
        have = set(db.scalars(select(EmbeddingCache.cache_key).where(EmbeddingCache.cache_key.in_([k for k, _ in pairs]))))
        for k, v in pairs:
            if k not in have: db.add(EmbeddingCache(cache_key=k, vector=v)); have.add(k)
        try: db.commit()
        except IntegrityError: db.rollback()

# ---------- model routing ----------
ROUTER_PROMPT = ('คุณเลือกโมเดลภาษาให้ตอบคำถามจากเอกสารองค์กร เลือกโมเดลที่ถูกที่สุดที่ยังตอบได้ดี '
                 'คำถามง่าย ค้นข้อเท็จจริง หรือสรุปสั้น ให้เลือกโมเดลเล็กหรือราคาถูก ส่วนการวิเคราะห์ซับซ้อน เปรียบเทียบหลายเอกสาร '
                 'การคำนวณ หรือการให้เหตุผลเชิงลึก ให้เลือกโมเดลใหญ่ ตอบด้วย id ของโมเดลเพียงค่าเดียว ไม่ต้องอธิบาย')

async def route_model(db, question, evidence_chars, candidates, router_model):
    """Ask a cheap router model which allowed model should answer. Returns an AIModel or None to keep the default."""
    if len(candidates) < 2: return None
    url, key = gateway.configuration(db)
    if not url: return None
    listing = '\n'.join(f'{m.id} | {m.name} | ${m.input_price:g} เข้า / ${m.output_price:g} ออก ต่อ 1M โทเคน' for m in candidates)
    messages = [{'role': 'system', 'content': ROUTER_PROMPT},
                {'role': 'user', 'content': f'คำถาม: {question[:600]}\nขนาดหลักฐานที่แนบ: {evidence_chars} ตัวอักษร\nโมเดลที่เลือกได้:\n{listing}'}]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=4)) as client:
            r = await client.post(url + '/chat/completions', headers=gateway.headers(key), json={'model': router_model, 'messages': messages, 'max_tokens': 60, 'temperature': 0, **gateway.routing('', url)})
            r.raise_for_status()
            out = r.json()['choices'][0]['message']['content'] or ''
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None
    return next((m for m in candidates if m.id in out), None) or next((m for m in candidates if m.api_id in out), None)

# ---------- prompt caching ----------
def apply_prompt_cache(messages, api_id):
    """Mark the stable prefix (system prompt and earlier turns) as cacheable for providers that need an explicit marker."""
    if not any(x in api_id.lower() for x in ('claude', 'anthropic')) or len(messages) < 2: return messages
    out = [dict(m) for m in messages]
    for i in {0, len(out) - 2}:
        text = out[i]['content']
        if isinstance(text, str): out[i]['content'] = [{'type': 'text', 'text': text, 'cache_control': {'type': 'ephemeral'}}]
    return out

# ---------- limits and alerts ----------
def enforce_limits(db, u, p):
    now = utc_now()
    if p['rate_per_minute']:
        recent = db.scalar(select(func.count()).select_from(Usage).where(Usage.user_id == u.id, ~Usage.model.startswith('เสียง · พูด'), ~Usage.model.startswith('แปลคำค้น'), Usage.created_at >= (now - timedelta(minutes=1)).isoformat()))
        if recent >= p['rate_per_minute']: raise HTTPException(429, f'ส่งคำขอถี่เกินไป (สูงสุด {p["rate_per_minute"]} ครั้งต่อนาที) กรุณารอสักครู่')
    if p['daily_requests']:
        today = db.scalar(select(func.count()).select_from(Usage).where(Usage.user_id == u.id, ~Usage.model.startswith('เสียง · พูด'), ~Usage.model.startswith('แปลคำค้น'), Usage.created_at >= now.strftime('%Y-%m-%d')))
        if today >= p['daily_requests']: raise HTTPException(429, f'ใช้ครบ {p["daily_requests"]} คำขอต่อวันแล้ว กรุณาลองใหม่พรุ่งนี้')

def check_budget_alerts(tenant_id, user_id):
    """Raise an admin alert once usage crosses the configured share of the user or organisation budget."""
    try:
        month = utc_now().strftime('%Y-%m')
        with SessionLocal() as db:
            percent = policy(db, tenant_id)['alert_percent']
            user = db.get(User, user_id)
            spend = lambda *w: float(db.scalar(select(func.coalesce(func.sum(Usage.cost), 0)).where(*w, Usage.created_at.startswith(month))))
            if user and user.monthly_budget:
                used = spend(Usage.user_id == user_id)
                if used >= user.monthly_budget * percent / 100:
                    alerts.publish(f'user-budget:{user_id}:{month}', f'{user.name} ใช้งบถึง {used / user.monthly_budget * 100:.0f}% ของโควตา',
                                   f'${used:.2f} จาก ${user.monthly_budget:.2f} ในเดือน {month}', tenant_id=tenant_id, user_id=user_id, severity='warning' if used < user.monthly_budget else 'critical')
            mp = db.scalar(select(ModelPolicy).where(ModelPolicy.tenant_id == tenant_id))
            if mp and mp.monthly_budget:
                used = spend(Usage.tenant_id == tenant_id)
                if used >= mp.monthly_budget * percent / 100:
                    alerts.publish(f'org-budget:{tenant_id}:{month}', f'องค์กรใช้งบถึง {used / mp.monthly_budget * 100:.0f}% ของงบประมาณ',
                                   f'${used:.2f} จาก ${mp.monthly_budget:.2f} ในเดือน {month}', tenant_id=tenant_id, severity='warning' if used < mp.monthly_budget else 'critical')
    except Exception:
        pass  # alerts must never break a request

# ---------- report ----------
@router.get('/savings/report')
def report(days: int = Query(30, ge=1, le=365), u: User = Depends(admin), db: Session = Depends(db_session)):
    cutoff = (utc_now() - timedelta(days=days)).isoformat()
    month = utc_now().strftime('%Y-%m')
    base = [Usage.tenant_id == u.tenant_id, Usage.created_at >= cutoff]
    by_model = [{'model': m, 'requests': n, 'cost': c} for m, n, c in db.execute(select(Usage.model, func.count(), func.coalesce(func.sum(Usage.cost), 0)).where(*base).group_by(Usage.model).order_by(func.sum(Usage.cost).desc()).limit(10))]
    top_users = [{'name': n, 'email': e, 'requests': r, 'cost': c} for n, e, r, c in db.execute(select(User.name, User.email, func.count(), func.coalesce(func.sum(Usage.cost), 0)).join(User, User.id == Usage.user_id).where(*base).group_by(User.id).order_by(func.sum(Usage.cost).desc()).limit(10))]
    by_department = [{'name': n, 'requests': r, 'cost': c} for n, r, c in db.execute(select(Group.name, func.count(), func.coalesce(func.sum(Usage.cost), 0)).select_from(Usage).join(GroupMember, GroupMember.user_id == Usage.user_id).join(Group, Group.id == GroupMember.group_id).where(*base, Group.kind == 'department').group_by(Group.id).order_by(func.sum(Usage.cost).desc()))]
    ev = {k: (n, s) for k, n, s in db.execute(select(SavingsEvent.kind, func.count(), func.coalesce(func.sum(SavingsEvent.saved), 0)).where(SavingsEvent.tenant_id == u.tenant_id, SavingsEvent.created_at >= cutoff).group_by(SavingsEvent.kind))}
    routed = {d: n for d, n in db.execute(select(SavingsEvent.detail, func.count()).where(SavingsEvent.tenant_id == u.tenant_id, SavingsEvent.kind == 'route', SavingsEvent.created_at >= cutoff).group_by(SavingsEvent.detail))}
    spent = float(db.scalar(select(func.coalesce(func.sum(Usage.cost), 0)).where(Usage.tenant_id == u.tenant_id, Usage.created_at.startswith(month))))
    mp = db.scalar(select(ModelPolicy).where(ModelPolicy.tenant_id == u.tenant_id))
    cached = db.scalar(select(func.count()).select_from(AnswerCache).where(AnswerCache.tenant_id == u.tenant_id, AnswerCache.expires_at > utc_now().isoformat()))
    return {'days': days, 'by_model': by_model, 'top_users': top_users, 'by_department': by_department,
            'month': {'month': month, 'spent': spent, 'budget': mp.monthly_budget if mp else 0},
            'savings': {'cache_hits': ev.get('cache_hit', (0, 0))[0], 'cache_saved': ev.get('cache_hit', (0, 0))[1], 'embedding_batches_cached': ev.get('embedding_hit', (0, 0))[0],
                        'routed': ev.get('route', (0, 0))[0], 'routed_to': routed, 'cached_answers': cached}}

# ---------- media ----------
def estimate_cost(db, tenant_id, model_id):
    """Average of this organisation's recent priced jobs for the model, or None when there is no history."""
    costs = list(db.scalars(select(GenerationJob.cost).where(GenerationJob.tenant_id == tenant_id, GenerationJob.model_id == model_id, GenerationJob.status == 'completed', GenerationJob.cost_known == True).order_by(GenerationJob.created_at.desc()).limit(20)))
    if costs: return round(sum(costs) / len(costs), 6)
    # No history yet: fall back to the OpenRouter reference price (image = USD per image, video = USD per second x 5 s).
    m = db.get(AIModel, model_id)
    if m and m.output_price and m.category in ('Image', 'Video'): return round(m.output_price * (5 if m.category == 'Video' else 1), 6)
    return None

def media_spent_today(db, u):
    """USD this user's image/video jobs cost today (finished jobs at their real cost; queued or running ones are not counted until done)."""
    today = utc_now().strftime('%Y-%m-%d')
    return float(db.scalar(select(func.coalesce(func.sum(GenerationJob.cost), 0)).where(GenerationJob.user_id == u.id, GenerationJob.kind.in_(['image', 'video']), GenerationJob.status == 'completed', GenerationJob.created_at >= today)))

def media_remaining(db, u, p):
    if not p['media_daily_limit']: return None
    today = utc_now().strftime('%Y-%m-%d')
    used = db.scalar(select(func.count()).select_from(GenerationJob).where(GenerationJob.user_id == u.id, GenerationJob.created_at >= today))
    return max(0, p['media_daily_limit'] - used)

@router.get('/media/estimate')
def media_estimate(model_id: str, u: User = Depends(current_user), db: Session = Depends(db_session)):
    p = policy(db, u.tenant_id)
    est = estimate_cost(db, u.tenant_id, model_id)
    return {'cost': est, 'remaining_today': media_remaining(db, u, p), 'daily_usd': p['media_daily_usd'], 'spent_today': round(media_spent_today(db, u), 6),
            'needs_approval': bool(p['media_approval_usd'] and est is not None and est >= p['media_approval_usd']), 'approval_usd': p['media_approval_usd']}

@router.get('/media/approvals')
def approvals(u: User = Depends(admin), db: Session = Depends(db_session)):
    rows = db.execute(select(GenerationJob, User.name, User.email).join(User, User.id == GenerationJob.user_id).where(GenerationJob.tenant_id == u.tenant_id, GenerationJob.status == 'awaiting_approval').order_by(GenerationJob.created_at))
    return [{'id': j.id, 'kind': j.kind, 'prompt': j.prompt[:300], 'user': n, 'email': e, 'estimate': estimate_cost(db, u.tenant_id, j.model_id), 'created_at': j.created_at} for j, n, e in rows]

def pending_job(db, u, id):
    j = db.scalar(select(GenerationJob).where(GenerationJob.id == id, GenerationJob.tenant_id == u.tenant_id, GenerationJob.status == 'awaiting_approval'))
    if not j: raise HTTPException(404, 'ไม่พบงานที่รออนุมัติ')
    return j

@router.post('/media/jobs/{id}/approve')
def approve(id: str, background: BackgroundTasks, u: User = Depends(admin), db: Session = Depends(db_session)):
    j = pending_job(db, u, id); j.status = 'queued'; j.updated_at = utc_now().isoformat(); db.commit()
    log(db, u, 'อนุมัติงานสร้างสื่อ', j.kind)
    from .jobs import schedule_media
    schedule_media(j.id, background)
    return {'ok': True}

@router.post('/media/jobs/{id}/reject')
def reject(id: str, u: User = Depends(admin), db: Session = Depends(db_session)):
    j = pending_job(db, u, id); j.status = 'failed'; j.error = 'ผู้ดูแลไม่อนุมัติงานนี้'; j.updated_at = utc_now().isoformat(); db.commit()
    log(db, u, 'ไม่อนุมัติงานสร้างสื่อ', j.kind)
    return {'ok': True}
