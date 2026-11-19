import os, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
_test_root=Path(__file__).resolve().parents[1]/'data'/'tests'
_test_root.mkdir(parents=True,exist_ok=True)
_tmp=tempfile.mkdtemp(prefix='hub-test-',dir=_test_root)
os.environ['DATA_DIR']=_tmp
from hub.scratch_db import create as _create_database  # tests run on a throw-away database in the Compose PostgreSQL
os.environ['DATABASE_URL'],_drop_database=_create_database('hub_test')
os.environ.pop('MIGRATION_DATABASE_URL',None)
import atexit; atexit.register(_drop_database)
os.environ['SEED_SAMPLE_DATA']='true'
os.environ['SEED_SAMPLE_SKILLS']='false'  # the skill tests count skills; tests of the samples switch it on
for key in ('S3_ENDPOINT','QDRANT_URL','CELERY_BROKER_URL','APP_ENV','LITELLM_URL','CLAMAV_HOST','CLAMAV_REQUIRED','BACKUP_DIR'): os.environ.pop(key,None)
import pytest
from fastapi.testclient import TestClient
from hub.main import app, windows
from hub.database import Base, engine, SessionLocal
from hub.models import Organization, User, KnowledgeBase
from hub.auth import passwords

@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    """Default test gateway: answers every chat call by quoting the evidence it was given, like a grounded model would."""
    import httpx
    monkeypatch.setenv('LITELLM_URL','http://gateway.test/v1')
    monkeypatch.setenv('QUERY_TRANSLATION','false')  # tests of the translation switch it on
    def respond(request):
        body=__import__('json').loads(request.content);user=str(body['messages'][-1]['content'])
        evidence=user.split('หลักฐาน:',1)[1].strip() if 'หลักฐาน:' in user else ''
        text='คำตอบทดสอบ'+(chr(10)*2+evidence if evidence else '')
        return httpx.Response(200,json={'choices':[{'message':{'content':text}}],'usage':{'prompt_tokens':10,'completion_tokens':5}})
    real=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda *a,**kw:real(*a,**{'transport':httpx.MockTransport(respond),**kw}))

@pytest.fixture
def client():
    Base.metadata.drop_all(engine); windows.clear()
    from hub import antivirus; antivirus.forget()
    with TestClient(app) as c: yield c

def login_as(client,role):
    """Sign in as one of the accounts created by the test seed (member, department, admin)."""
    from hub.seed import DATA
    return client.post('/api/auth/login',json={'email':f'{role}@local.test','password':(DATA/'dev-password.txt').read_text(encoding='utf-8')})

@pytest.fixture
def member(client):
    assert login_as(client,'member').status_code==200
    return client

@pytest.fixture
def department(client):
    assert login_as(client,'department').status_code==200
    return client

@pytest.fixture
def admin(client):
    assert login_as(client,'admin').status_code==200
    return client

@pytest.fixture
def other_tenant():
    with SessionLocal() as db:
        o=Organization(name='Tenant B');db.add(o);db.flush()
        u=User(tenant_id=o.id,email='b@example.test',name='B',role='DEPARTMENT_ADMIN',password_hash=passwords.hash('testing-password-B'))
        k=KnowledgeBase(tenant_id=o.id,name='ความลับของ B');db.add_all([u,k]);db.commit()
        return {'org':o.id,'kb':k.id,'user':u.id}
