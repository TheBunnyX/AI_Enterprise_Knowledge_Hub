import hashlib, os, secrets
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from .database import SessionLocal, DATA
from .models import Organization, User, KnowledgeBase, Document, AIModel
from .feature_models import DocumentState
from .ops_models import Group, GroupMember
from .auth import passwords
from . import storage
from .retrieval import ingest

SAMPLES = Path(__file__).parent / 'sample_docs'
# starter documents: file name -> knowledge base (department)
STARTER = {'นโยบายการทำงานแบบยืดหยุ่น (Hybrid Working).pdf':'ฝ่ายทรัพยากรบุคคล','แผนกลยุทธ์องค์กร 2026–2028.pdf':'ฝ่ายกลยุทธ์','คู่มือความปลอดภัยในการทำงาน.pdf':'ความปลอดภัย','แนวทางการใช้ AI ภายในองค์กร.pdf':'เทคโนโลยีสารสนเทศ'}
# plain-text placeholders used before the real PDFs existed
LEGACY = ['นโยบายการทำงานแบบยืดหยุ่น (Hybrid Working).txt','แผนกลยุทธ์องค์กร 2026–2028.txt','คู่มือความปลอดภัยในการทำงาน.txt','แนวทางการใช้ AI ภายในองค์กร.md']

def ensure_real_documents(db,org_id):
    """Add the starter PDFs and move the old plain-text placeholders to the trash. Returns ids to ingest."""
    ids=[]
    for old in db.scalars(select(Document).where(Document.tenant_id==org_id,Document.name.in_(LEGACY))):
        state=db.scalar(select(DocumentState).where(DocumentState.document_id==old.id))
        if not state: db.add(DocumentState(tenant_id=org_id,document_id=old.id,deleted_at=datetime.now(timezone.utc).isoformat()))
    for name,dept in STARTER.items():
        path=SAMPLES/name
        if not path.exists() or db.scalar(select(Document).where(Document.tenant_id==org_id,Document.name==name)): continue
        kb=db.scalar(select(KnowledgeBase).where(KnowledgeBase.tenant_id==org_id,KnowledgeBase.name==dept))
        if not kb: kb=KnowledgeBase(tenant_id=org_id,name=dept,description='คลังเอกสารองค์กร'); db.add(kb); db.flush()
        elif kb.description=='คลังเอกสารตัวอย่าง': kb.description='คลังเอกสารองค์กร'
        raw=path.read_bytes(); key=f'{org_id}/{secrets.token_hex(12)}'; storage.put(key,raw)
        d=Document(tenant_id=org_id,knowledge_base_id=kb.id,name=name,sha256=hashlib.sha256(raw).hexdigest(),size=len(raw),storage_key=key)
        db.add(d); db.flush(); ids.append(d.id)
    db.commit()
    return ids

def ensure_department_demo(db):
    """Databases seeded before the department-admin role lack its demo account."""
    admin=db.scalar(select(User).where(User.email=='admin@local.test'))
    if not admin or db.scalar(select(User).where(User.email=='department@local.test')): return
    password_file=DATA/'dev-password.txt'
    if not password_file.exists(): return
    user=User(tenant_id=admin.tenant_id,email='department@local.test',name='สมหญิง รักงาน',role='DEPARTMENT_ADMIN',password_hash=passwords.hash(password_file.read_text(encoding='utf-8').strip()))
    db.add(user); db.flush()
    department=db.scalar(select(Group).where(Group.tenant_id==admin.tenant_id,Group.name=='ฝ่ายบุคคล'))
    if not department: department=Group(tenant_id=admin.tenant_id,name='ฝ่ายบุคคล',kind='department'); db.add(department); db.flush()
    member=db.scalar(select(User).where(User.email=='member@local.test'))
    for u in (user,member):
        if u and not db.scalar(select(GroupMember).where(GroupMember.group_id==department.id,GroupMember.user_id==u.id)): db.add(GroupMember(tenant_id=admin.tenant_id,group_id=department.id,user_id=u.id))
    db.commit()

def seed():
    if os.getenv('SEED_SAMPLE_DATA','false').lower()!='true': return  # production data is created by hub.bootstrap, never seeded
    ids=[]
    with SessionLocal() as db:
        existing=db.scalar(select(Organization).order_by(Organization.created_at).limit(1))
        if existing:
            ensure_department_demo(db); ids=ensure_real_documents(db,existing.id)
            for i in ids: ingest(i)
            return
        org=Organization(name='องค์กรสาธิต AI Knowledge Hub',plan='Enterprise'); db.add(org); db.flush()
        password=secrets.token_urlsafe(18); (DATA/'dev-password.txt').write_text(password,encoding='utf-8')
        demo={a.split('|')[1]:a.split('|')[2] for a in os.getenv('DEMO_ACCOUNTS','').split(';') if a.count('|')==2}  # demo sign-in buttons must match the seeded passwords
        for email,name,role in [('admin@local.test','ผู้ดูแลระบบ','SUPER_ADMIN'),('department@local.test','สมหญิง รักงาน','DEPARTMENT_ADMIN'),('member@local.test','สมชาย ใจดี','USER')]:
            db.add(User(tenant_id=org.id,email=email,name=name,role=role,password_hash=passwords.hash(demo.get(email,password))))
        db.flush()
        department=Group(tenant_id=org.id,name='ฝ่ายบุคคล',kind='department');db.add(department);db.flush()
        for user in db.scalars(select(User).where(User.email.in_(['department@local.test','member@local.test']))):db.add(GroupMember(tenant_id=org.id,group_id=department.id,user_id=user.id))
        db.commit(); ids=ensure_real_documents(db,org.id)
        db.add(AIModel(name='Test LLM',provider='LiteLLM',api_id='test-llm',enabled=True)); db.commit()  # sample-data (dev/test) databases only
    for i in ids: ingest(i)

def install_starter_documents():
    """One-off for existing databases: python -m hub.seed -- adds the starter PDFs and trashes the old placeholders."""
    with SessionLocal() as db:
        org=db.scalar(select(Organization).order_by(Organization.created_at).limit(1))
        if not org: return []
        ids=ensure_real_documents(db,org.id)
    for i in ids: ingest(i)
    return ids

if __name__=='__main__':
    print('added',len(install_starter_documents()),'documents')
