"""Live PostgreSQL check that row-level security isolates tenants: docker compose exec -T api python -m hub.rls_check"""
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from hub.database import SessionLocal, scope_to_tenant
from hub.models import Organization, User, Audit, Document
with SessionLocal() as db:
    print('role', db.scalar(text('select current_user')), 'super', db.scalar(text("select rolsuper from pg_roles where rolname=current_user")))
    orgs=list(db.scalars(select(Organization.id)));a=orgs[0]
    users=db.scalar(select(func.count()).select_from(User));docs=db.scalar(select(func.count()).select_from(Document))
    print('bypass users/docs',users,docs)
    b=Organization(name='rls-check-b');db.add(b);db.flush();db.add(Audit(tenant_id=b.id,actor='x',action='rls-check',detail=''));db.commit();bid=b.id
with SessionLocal() as db:
    scope_to_tenant(db,a)
    print('A sees users/docs',db.scalar(select(func.count()).select_from(User)),db.scalar(select(func.count()).select_from(Document)))
    print('A sees B audit rows',db.scalar(select(func.count()).select_from(Audit).where(Audit.tenant_id==bid)))
    db.add(Audit(tenant_id=bid,actor='x',action='rls-write',detail=''))
    try:db.commit();print('CROSS-TENANT WRITE ALLOWED (BAD)')
    except DBAPIError as e:print('cross-tenant write blocked:',str(e.orig).splitlines()[0]);db.rollback()
    scope_to_tenant(db,'no-such-tenant');print('empty tenant sees users',db.scalar(select(func.count()).select_from(User)))
with SessionLocal() as db:
    print('B audit rows via bypass',db.scalar(select(func.count()).select_from(Audit).where(Audit.tenant_id==bid)))
    db.query(Audit).filter(Audit.tenant_id==bid).delete();db.query(Organization).filter(Organization.id==bid).delete();db.commit();print('cleaned')
