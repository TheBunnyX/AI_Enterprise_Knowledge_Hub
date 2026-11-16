import hashlib, os, secrets, time
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from pwdlib import PasswordHash
from .database import db_session, scope_to_tenant
from .models import User, LoginSession, Organization, Audit
from .clientip import current_ip

PRODUCTION = os.getenv('APP_ENV') == 'production'
passwords = PasswordHash.recommended()

SEEN_EVERY = 30   # seconds between last_seen writes
ONLINE_WINDOW = 120  # a user counts as online if seen within this many seconds

def is_online(u): return time.time() - (u.last_seen or 0) < ONLINE_WINDOW

def current_user(request: Request, db: Session = Depends(db_session)):
    token = request.cookies.get('hub_session', '')
    s = db.scalar(select(LoginSession).where(LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest(), LoginSession.expires > time.time()))
    u = db.get(User, s.user_id) if s else None
    if not u or not u.active: raise HTTPException(401, 'กรุณาเข้าสู่ระบบ')
    org = db.get(Organization, u.tenant_id)
    if not org or org.status != 'active': raise HTTPException(403, 'องค์กรถูกระงับการใช้งาน')
    if time.time() - u.last_seen > SEEN_EVERY:
        db.execute(update(User).where(User.id == u.id).values(last_seen=time.time())); db.commit()
    # Members and department admins only ever see their own tenant's rows; super admins operate across tenants.
    if u.role != 'SUPER_ADMIN': scope_to_tenant(db, u.tenant_id)
    return u

def admin(u: User = Depends(current_user)):
    if u.role != 'SUPER_ADMIN': raise HTTPException(403, 'ต้องมีสิทธิ์ Super Admin')
    return u

def manager(u):
    if u.role not in ('SUPER_ADMIN', 'DEPARTMENT_ADMIN'): raise HTTPException(403, 'ต้องมีสิทธิ์ผู้ดูแลแผนกหรือ Super Admin')

def issue_session(db, user, response):
    token = secrets.token_urlsafe(48)
    db.add(LoginSession(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires=time.time()+28800))
    db.add(Audit(tenant_id=user.tenant_id, user_id=user.id, actor=user.name, action='เข้าสู่ระบบ', detail=user.email))
    db.execute(update(User).where(User.id == user.id).values(last_ip=current_ip.get()))
    db.commit()
    response.set_cookie('hub_session', token, httponly=True, secure=PRODUCTION, samesite='lax', max_age=28800, path='/')

def public_user(u):
    return {k:getattr(u,k) for k in ('id','name','email','role','tenant_id')}
