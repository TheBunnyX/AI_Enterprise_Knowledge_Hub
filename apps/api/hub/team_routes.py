"""User management for Super Admins and department admins.

A department admin only reaches accounts that are plain USERs in a department they belong to.
Role changes stay on the Super Admin only /admin/users endpoints.
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session
from .database import db_session
from .models import User, Usage, Organization, Audit
from .ops_models import Group, GroupMember
from .auth import current_user, manager, passwords, public_user, admin, is_online
from .models import LoginSession
from .policies import month_spend

router = APIRouter(prefix='/api/team')

def log(db, u, action, detail=''):
    db.add(Audit(tenant_id=u.tenant_id, user_id=u.id, actor=u.name, action=action, detail=detail)); db.commit()

def departments(db, u):
    return list(db.scalars(select(Group.id).join(GroupMember, GroupMember.group_id == Group.id).where(
        Group.tenant_id == u.tenant_id, Group.kind == 'department', GroupMember.user_id == u.id, GroupMember.tenant_id == u.tenant_id)))

def scope(db, u, tenant_id=None):
    """Statement selecting the users the caller may manage."""
    manager(u)
    if u.role == 'SUPER_ADMIN':
        stmt = select(User)
        return stmt.where(User.tenant_id == tenant_id) if tenant_id else stmt
    own = departments(db, u)
    if not own: return select(User).where(User.id == '')
    members = select(GroupMember.user_id).where(GroupMember.group_id.in_(own), GroupMember.tenant_id == u.tenant_id)
    return select(User).where(User.tenant_id == u.tenant_id, User.role == 'USER', User.id.in_(members), User.id != u.id)

def target(db, u, id):
    a = db.scalar(scope(db, u).where(User.id == id))
    if not a: raise HTTPException(404, 'ไม่พบผู้ใช้ในขอบเขตที่คุณดูแล')
    if a.id == u.id: raise HTTPException(400, 'ไม่สามารถจัดการบัญชีตนเองจากหน้านี้')
    return a

def serialize(a, usage, depts, month=0.0):
    return {**public_user(a), 'active': a.active, 'online': is_online(a), 'created_at': a.created_at, 'departments': depts.get(a.id, []),
            'requests': usage[0] if usage else 0, 'input_tokens': usage[1] if usage else 0,
            'output_tokens': usage[2] if usage else 0, 'cost': usage[3] if usage else 0,
            'monthly_budget': a.monthly_budget, 'month_spend': month}

@router.get('/users')
def list_users(days: int = Query(30, ge=1, le=365), tenant_id: str | None = None, department_id: str | None = None, u: User = Depends(current_user), db: Session = Depends(db_session)):
    stmt = scope(db, u, tenant_id)
    if department_id:
        dept = department_for(db, u, department_id)
        stmt = stmt.where(User.id.in_(select(GroupMember.user_id).where(GroupMember.group_id == dept.id, GroupMember.tenant_id == dept.tenant_id)))
    users = list(db.scalars(stmt.order_by(User.name)))
    ids = [a.id for a in users]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    usage = {r[0]: r[1:] for r in db.execute(select(Usage.user_id, func.count(), func.coalesce(func.sum(Usage.input_tokens), 0), func.coalesce(func.sum(Usage.output_tokens), 0), func.coalesce(func.sum(Usage.cost), 0)).where(Usage.user_id.in_(ids), Usage.created_at >= cutoff).group_by(Usage.user_id))} if ids else {}
    depts = {}
    if ids:
        for uid, name in db.execute(select(GroupMember.user_id, Group.name).join(Group, Group.id == GroupMember.group_id).where(GroupMember.user_id.in_(ids), Group.kind == 'department')):
            depts.setdefault(uid, []).append(name)
    return [serialize(a, usage.get(a.id), depts, month_spend(db, a.id)) for a in users]

class TeamUserInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$', max_length=254)
    password: str = Field(min_length=12, max_length=200)
    tenant_id: str | None = None
    department_id: str | None = None

@router.post('/users', status_code=201)
def create_user(body: TeamUserInput, u: User = Depends(current_user), db: Session = Depends(db_session)):
    manager(u)
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)): raise HTTPException(409, 'อีเมลนี้มีอยู่แล้ว')
    if u.role == 'SUPER_ADMIN':
        tenant = body.tenant_id or u.tenant_id
        if not db.get(Organization, tenant): raise HTTPException(404, 'ไม่พบองค์กร')
        dept = body.department_id
        if not dept: raise HTTPException(422, 'ผู้ใช้ทุกคนต้องอยู่ในฝ่าย กรุณาเลือกฝ่าย')
    else:
        own = departments(db, u)
        tenant = u.tenant_id
        dept = body.department_id or (own[0] if len(own) == 1 else None)
        if not dept or dept not in own: raise HTTPException(422, 'เลือกแผนกที่คุณดูแล')
    if dept and not db.scalar(select(Group).where(Group.id == dept, Group.tenant_id == tenant, Group.kind == 'department')): raise HTTPException(422, 'ไม่พบแผนก')
    a = User(tenant_id=tenant, email=email, name=body.name, role='USER', password_hash=passwords.hash(body.password))
    db.add(a); db.flush()
    if dept: db.add(GroupMember(tenant_id=tenant, group_id=dept, user_id=a.id))
    db.commit(); log(db, u, 'เพิ่มผู้ใช้', a.email)
    return public_user(a)

class TeamNameInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)

@router.put('/users/{id}')
def rename_user(id: str, body: TeamNameInput, u: User = Depends(current_user), db: Session = Depends(db_session)):
    a = target(db, u, id); a.name = body.name; db.commit(); log(db, u, 'แก้ไขชื่อผู้ใช้', a.email)
    return {'ok': True}

@router.post('/users/{id}/toggle')
def toggle_user(id: str, u: User = Depends(current_user), db: Session = Depends(db_session)):
    a = target(db, u, id); a.active = not a.active
    db.execute(delete(LoginSession).where(LoginSession.user_id == a.id)); db.commit()
    log(db, u, 'เปลี่ยนสถานะผู้ใช้', a.email)
    return {'active': a.active}

class TeamQuotaInput(BaseModel):
    monthly_budget: float = Field(ge=0, le=1000000)

@router.put('/users/{id}/quota')
def set_quota(id: str, body: TeamQuotaInput, u: User = Depends(current_user), db: Session = Depends(db_session)):
    """Monthly budget in USD for one user; 0 means unlimited. Nobody sets their own."""
    a = target(db, u, id); a.monthly_budget = round(body.monthly_budget, 4); db.commit()
    log(db, u, 'กำหนดโควตาการใช้งานรายเดือน', f'{a.email} · {"$" + format(a.monthly_budget, ".2f") if a.monthly_budget else "ไม่จำกัด"}')
    return {'monthly_budget': a.monthly_budget}

class TeamPasswordInput(BaseModel):
    password: str = Field(min_length=12, max_length=200)

@router.post('/users/{id}/password')
def reset_password(id: str, body: TeamPasswordInput, u: User = Depends(current_user), db: Session = Depends(db_session)):
    a = target(db, u, id); a.password_hash = passwords.hash(body.password)
    db.execute(delete(LoginSession).where(LoginSession.user_id == a.id)); db.commit()
    log(db, u, 'รีเซ็ตรหัสผ่านผู้ใช้', a.email)
    return {'ok': True}

# ---- Departments (ฝ่าย) of the single organization ----

def department_for(db, u, id):
    """A department the caller may work in: any in their tenant for Super Admins, only their own otherwise."""
    manager(u)
    g = db.scalar(select(Group).where(Group.id == id, Group.kind == 'department', Group.tenant_id == u.tenant_id))
    if not g or (u.role != 'SUPER_ADMIN' and g.id not in departments(db, u)): raise HTTPException(404, 'ไม่พบฝ่าย')
    return g

def describe(db, g):
    members = list(db.scalars(select(User).join(GroupMember, GroupMember.user_id == User.id).where(GroupMember.group_id == g.id, GroupMember.tenant_id == g.tenant_id).order_by(User.name)))
    return {'id': g.id, 'name': g.name, 'members': len(members), 'active_members': sum(1 for m in members if m.active),
            'admins': [m.name for m in members if m.role == 'DEPARTMENT_ADMIN']}

@router.get('/departments')
def list_departments(u: User = Depends(current_user), db: Session = Depends(db_session)):
    manager(u)
    stmt = select(Group).where(Group.tenant_id == u.tenant_id, Group.kind == 'department')
    if u.role != 'SUPER_ADMIN': stmt = stmt.where(Group.id.in_(departments(db, u) or ['']))
    return [describe(db, g) for g in db.scalars(stmt.order_by(Group.name))]

class DepartmentInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)

@router.post('/departments', status_code=201)
def create_department(body: DepartmentInput, u: User = Depends(admin), db: Session = Depends(db_session)):
    if db.scalar(select(Group).where(Group.tenant_id == u.tenant_id, Group.name == body.name)): raise HTTPException(409, 'ชื่อฝ่ายนี้มีอยู่แล้ว')
    g = Group(tenant_id=u.tenant_id, name=body.name, kind='department'); db.add(g); db.commit()
    log(db, u, 'สร้างฝ่าย', g.name)
    return describe(db, g)

@router.put('/departments/{id}')
def rename_department(id: str, body: DepartmentInput, u: User = Depends(admin), db: Session = Depends(db_session)):
    g = department_for(db, u, id)
    if db.scalar(select(Group).where(Group.tenant_id == u.tenant_id, Group.name == body.name, Group.id != g.id)): raise HTTPException(409, 'ชื่อฝ่ายนี้มีอยู่แล้ว')
    g.name = body.name; db.commit(); log(db, u, 'เปลี่ยนชื่อฝ่าย', g.name)
    return {'ok': True}

@router.delete('/departments/{id}')
def delete_department(id: str, u: User = Depends(admin), db: Session = Depends(db_session)):
    g = department_for(db, u, id)
    if db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == g.id)): raise HTTPException(409, 'ลบไม่ได้ ยังมีสมาชิกในฝ่ายนี้ ให้ย้ายสมาชิกออกก่อน')
    name = g.name; db.delete(g); db.commit(); log(db, u, 'ลบฝ่าย', name)
    return {'ok': True}

@router.get('/departments/{id}/candidates')
def candidates(id: str, u: User = Depends(current_user), db: Session = Depends(db_session)):
    """Existing accounts that can be added: Super Admin picks any tenant user not yet in the department;
    a department admin only picks plain users who belong to no department yet."""
    g = department_for(db, u, id)
    inside = select(GroupMember.user_id).where(GroupMember.group_id == g.id)
    stmt = select(User).where(User.tenant_id == g.tenant_id, User.active == True, User.id.notin_(inside))
    if u.role != 'SUPER_ADMIN':
        anywhere = select(GroupMember.user_id).join(Group, Group.id == GroupMember.group_id).where(Group.kind == 'department', Group.tenant_id == g.tenant_id)
        stmt = stmt.where(User.role == 'USER', User.id.notin_(anywhere))
    return [public_user(a) for a in db.scalars(stmt.order_by(User.name))]

class MemberInput(BaseModel):
    user_id: str

@router.post('/departments/{id}/members', status_code=201)
def add_member(id: str, body: MemberInput, u: User = Depends(current_user), db: Session = Depends(db_session)):
    g = department_for(db, u, id)
    if body.user_id not in [c['id'] for c in candidates(id, u, db)]: raise HTTPException(404, 'ไม่พบผู้ใช้ที่เพิ่มเข้าฝ่ายนี้ได้')
    db.add(GroupMember(tenant_id=g.tenant_id, group_id=g.id, user_id=body.user_id)); db.commit()
    log(db, u, 'เพิ่มสมาชิกเข้าฝ่าย', f'{g.name}')
    return {'ok': True}

@router.delete('/departments/{id}/members/{user_id}')
def remove_member(id: str, user_id: str, u: User = Depends(current_user), db: Session = Depends(db_session)):
    g = department_for(db, u, id)
    if user_id == u.id: raise HTTPException(400, 'ไม่สามารถนำตนเองออกจากฝ่าย')
    if u.role != 'SUPER_ADMIN': target(db, u, user_id)
    row = db.scalar(select(GroupMember).where(GroupMember.group_id == g.id, GroupMember.user_id == user_id))
    if not row: raise HTTPException(404, 'ผู้ใช้ไม่ได้อยู่ในฝ่ายนี้')
    who = db.get(User, user_id)
    if who and who.role != 'SUPER_ADMIN' and db.scalar(select(func.count()).select_from(GroupMember).join(Group, Group.id == GroupMember.group_id).where(GroupMember.user_id == user_id, Group.kind == 'department')) <= 1:
        raise HTTPException(409, 'ผู้ใช้ต้องอยู่ในฝ่ายอย่างน้อยหนึ่งฝ่าย ให้เพิ่มเข้าฝ่ายอื่นก่อนจึงจะนำออกจากฝ่ายนี้ได้')
    db.delete(row); db.commit(); log(db, u, 'นำสมาชิกออกจากฝ่าย', g.name)
    return {'ok': True}
