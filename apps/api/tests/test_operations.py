from conftest import login_as
import hashlib,time,io
from pathlib import Path
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from hub.database import SessionLocal
from hub.models import User,Document,Message
from hub.ops_models import TaskRun,SystemAlert,GroupMember
from hub.feature_models import GenerationJob
from hub import antivirus,backups,jobs,alerts
from test_platform import upload

class Socket:
    def __init__(self,response):self.response=response;self.sent=b''
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def sendall(self,data):self.sent+=data
    def recv(self,n):r=self.response;self.response=b'';return r

def test_antivirus_protocol_and_no_persistence_on_detection(admin,monkeypatch):
    monkeypatch.setenv('CLAMAV_HOST','test-scanner')
    sock=Socket(b'stream: Test-Signature FOUND\0')
    monkeypatch.setattr(antivirus.socket,'create_connection',lambda *a,**k:sock)
    before=len(admin.get('/api/documents').json())
    assert upload(admin,'harmless scanner test marker').status_code==422
    assert len(admin.get('/api/documents').json())==before
    assert sock.sent.startswith(b'zINSTREAM\0')
    assert any('อันตราย' in a['title'] for a in admin.get('/api/notifications').json())

def test_antivirus_unavailable_fails_closed(admin,monkeypatch):
    monkeypatch.setenv('CLAMAV_HOST','test-scanner')
    def failed(*a,**k):raise OSError()
    monkeypatch.setattr(antivirus.socket,'create_connection',failed)
    assert upload(admin,'will not be stored').status_code==503

def test_clean_antivirus_stream(monkeypatch):
    monkeypatch.setenv('CLAMAV_HOST','test-scanner');sock=Socket(b'stream: OK\0')
    monkeypatch.setattr(antivirus.socket,'create_connection',lambda *a,**k:sock)
    assert antivirus.scan(b'normal document')=='clean'
    assert sock.sent.endswith(b'\0\0\0\0')

def test_groups_document_acl_and_revocation(admin,other_tenant):
    users=admin.get('/api/admin/users').json();member=next(u for u in users if u['role']=='USER')['id']
    kb=admin.get('/api/knowledge-bases').json()[0]['id'];doc=upload(admin,'Group-private policy',kb=kb).json()['id']
    group=admin.post('/api/groups',json={'name':'กลุ่ม HR','kind':'group','members':[member]}).json()['id']
    assert admin.put('/api/groups/'+group,json={'name':'HR','members':[other_tenant['user']]}).status_code==422
    admin.put('/api/access/knowledge_base/'+kb,json={'visibility':'restricted','reader_groups':[group],'writer_groups':[group]})
    admin.put('/api/access/document/'+doc,json={'visibility':'restricted','reader_groups':[group]})
    login_as(admin,'member')
    assert admin.get('/api/documents/'+doc).status_code==200
    assert admin.post('/api/documents/'+doc+'/versions',files={'file':('v2.txt',b'new version','text/plain')}).status_code==404
    login_as(admin,'admin')
    admin.put('/api/groups/'+group,json={'name':'HR','members':[]})
    login_as(admin,'member')
    assert admin.get('/api/documents/'+doc).status_code==404
    assert admin.get('/api/documents/'+doc+'/download').status_code==404
    assert doc not in [x['id'] for x in admin.get('/api/documents').json()]
    assert admin.get('/api/search',params={'q':'Group-private','kb_id':kb}).json()==[]

def test_document_write_group_can_add_version(admin):
    member=next(u['id'] for u in admin.get('/api/admin/users').json() if u['role']=='USER')
    doc=upload(admin,'document original').json()['id']
    g=admin.post('/api/groups',json={'name':'Editors','members':[member]}).json()['id']
    admin.put('/api/access/document/'+doc,json={'visibility':'restricted','writer_groups':[g]})
    login_as(admin,'member')
    assert next(d for d in admin.get('/api/documents').json() if d['id']==doc)['can_write']
    assert admin.post('/api/documents/'+doc+'/versions',files={'file':('v2.txt',b'editor version','text/plain')}).status_code==200

def test_shared_conversation_respects_file_permissions_and_tenant(admin,other_tenant):
    member=next(u['id'] for u in admin.get('/api/admin/users').json() if u['role']=='USER')
    response=admin.post('/api/chat',json={'question':'ลาพักร้อน'})
    import json
    cid=json.loads(response.text.splitlines()[0])['conversation_id']
    assert admin.put('/api/conversations/'+cid+'/sharing',json={'users':[other_tenant['user']]}).status_code==422
    assert admin.put('/api/conversations/'+cid+'/sharing',json={'users':[member]}).status_code==200
    login_as(admin,'member')
    assert cid in [c['id'] for c in admin.get('/api/shared-conversations').json()]
    assert admin.get('/api/shared-conversations/'+cid).status_code==200
    assert admin.post('/api/chat',json={'question':'reply','conversation_id':cid}).status_code==404
    login_as(admin,'admin')
    citations=admin.get('/api/conversations/'+cid).json()[-1]['citations']
    for citation in citations:admin.put('/api/access/document/'+citation['document_id'],json={'visibility':'restricted'})
    login_as(admin,'member')
    assert admin.get('/api/shared-conversations/'+cid).status_code==404
    assert cid not in [c['id'] for c in admin.get('/api/shared-conversations').json()]

def test_sharing_rejects_recipient_without_access(admin):
    member=next(u['id'] for u in admin.get('/api/admin/users').json() if u['role']=='USER')
    response=admin.post('/api/chat',json={'question':'ลาพักร้อน'})
    import json
    cid=json.loads(response.text.splitlines()[0])['conversation_id'];refs=admin.get('/api/conversations/'+cid).json()[-1]['citations']
    for ref in refs:admin.put('/api/access/document/'+ref['document_id'],json={'visibility':'restricted'})
    assert admin.put('/api/conversations/'+cid+'/sharing',json={'users':[member]}).status_code==409

def test_job_deduplication_and_lease_recovery(admin,monkeypatch):
    doc=upload(admin,'idempotent document').json()['id']
    with SessionLocal() as db:
        run=db.scalar(select(TaskRun).where(TaskRun.target_id==doc));id=run.id;assert run.status=='completed';attempts=run.attempts
    assert jobs.schedule_ingest(doc)==id
    with SessionLocal() as db:
        run=db.get(TaskRun,id);assert run.attempts==attempts
        run.status='processing';run.lease_until=time.time()-1;run.next_attempt=0;db.commit()
    queued=[];monkeypatch.setattr(jobs,'enqueue',lambda id:queued.append(id))
    assert jobs.recover()['requeued']==1 and queued==[id]
    jobs.execute(id)
    with SessionLocal() as db:assert db.get(TaskRun,id).status=='completed'

def test_ambiguous_media_requires_review_without_rebill(admin,monkeypatch):
    u=admin.get('/api/auth/me').json();model=admin.get('/api/models').json()[0]['id']
    with SessionLocal() as db:
        j=GenerationJob(tenant_id=u['tenant_id'],user_id=u['id'],model_id=model,kind='image',status='processing');db.add(j);db.flush()
        r=TaskRun(task_key='media:'+j.id+':1',target_id=j.id,tenant_id=u['tenant_id'],kind='media',status='processing',attempts=1,lease_until=time.time()-1);db.add(r);db.commit();id=r.id
    queued=[];monkeypatch.setattr(jobs,'enqueue',lambda id:queued.append(id))
    assert jobs.recover()['review_required']==1 and not queued
    with SessionLocal() as db:assert db.get(TaskRun,id).status=='review_required'

def test_notification_dedup_and_read_state(admin):
    alerts.publish('test-service','บริการไม่พร้อม','ตรวจระบบ',severity='critical')
    first=admin.get('/api/notifications').json()[0];assert first['unread']
    admin.post('/api/notifications/read')
    alerts.publish('test-service','บริการไม่พร้อม','ตรวจระบบ',severity='critical')
    assert not admin.get('/api/notifications').json()[0]['unread']
    alerts.resolve('test-service')
    assert admin.get('/api/notifications').json()[0]['status']=='resolved'
    login_as(admin,'member')
    assert admin.get('/api/notifications').json()==[]

def test_encrypted_backup_integrity_and_isolation(tmp_path,monkeypatch):
    monkeypatch.setenv('BACKUP_ENCRYPTION_KEY','test-key-only')
    original=tmp_path/'plain';encrypted=tmp_path/'snapshot';restored=tmp_path/'restored';original.write_bytes(b'database and original files'*100)
    backups.encrypt(original,encrypted);assert b'database' not in encrypted.read_bytes()
    backups.decrypt(encrypted,restored);assert restored.read_bytes()==original.read_bytes()
    data=bytearray(encrypted.read_bytes());data[30]^=1;encrypted.write_bytes(data)
    with pytest.raises(Exception):backups.decrypt(encrypted,restored)
    from hub.database import URL
    with pytest.raises(ValueError,match='isolated'):backups.restore_snapshot('unused',URL)

def test_backup_and_operations_require_super_admin(member):
    for endpoint in ('/api/admin/backups','/api/admin/tasks','/api/admin/operations/health'):
        assert member.get(endpoint).status_code==403
    assert member.post('/api/admin/backups').status_code==403
    assert member.post('/api/admin/backups/none/restore',json={'confirmation':'RESTORE none'}).status_code==403

def test_pdf_endpoint_checks_type_and_permissions(admin):
    id=upload(admin,'not a PDF').json()['id']
    assert admin.get('/api/documents/'+id+'/pdf').status_code==415
    admin.put('/api/access/document/'+id,json={'visibility':'restricted'})
    login_as(admin,'member')
    assert admin.get('/api/documents/'+id+'/pdf').status_code==404


def test_restored_state_revokes_sessions_and_does_not_replay_jobs(admin):
    from hub.models import LoginSession
    id=upload(admin,'restore safety test').json()['id']
    with SessionLocal() as db:
        d=db.get(Document,id)
        task=TaskRun(task_key='restore-test',kind='ingest',target_id=id,tenant_id=d.tenant_id,status='processing',lease_token='old-worker',lease_until=time.time()+120)
        db.add(task);db.commit();task_id=task.id
        assert db.scalars(select(LoginSession)).first()
    assert id in backups.reset_restored_state()
    with SessionLocal() as db:
        assert not db.scalars(select(LoginSession)).first()
        task=db.get(TaskRun,task_id)
        assert task.status=='cancelled' and not task.lease_token and task.lease_until==0
    assert admin.get('/api/auth/me').status_code==401
