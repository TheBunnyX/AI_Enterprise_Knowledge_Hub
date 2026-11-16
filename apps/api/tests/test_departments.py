"""Department-based self-service: a department owns its knowledge bases, its admin manages them alone, sources keep them in sync."""
import pytest
from sqlalchemy import select
from hub.auth import passwords
from hub.database import SessionLocal
from hub.models import User, KnowledgeBase, Document
from hub.ops_models import Group, GroupMember
from conftest import login_as
from test_team import tenant_of, login, PW


def as_super(client):
    client.post('/api/auth/logout'); assert login_as(client, 'admin').status_code == 200


@pytest.fixture
def two_departments(client):
    """HR (admin h, member hm) and Finance (admin f); every account signs in with PW."""
    tenant = tenant_of('admin@local.test')
    with SessionLocal() as db:
        ids = {}
        for key, role in (('h', 'DEPARTMENT_ADMIN'), ('hm', 'USER'), ('f', 'DEPARTMENT_ADMIN'), ('plain', 'USER')):
            a = User(tenant_id=tenant, email=f'{key}@dept.test', name=key, role=role, password_hash=passwords.hash(PW)); db.add(a); db.flush(); ids[key] = a.id
        for name, members in (('HR', ('h', 'hm')), ('Finance', ('f',))):
            g = Group(tenant_id=tenant, name=name, kind='department'); db.add(g); db.flush(); ids[name] = g.id
            for m in members: db.add(GroupMember(tenant_id=tenant, group_id=g.id, user_id=ids[m]))
        db.commit()
    return ids


def make_kb(client, name, **extra):
    r = client.post('/api/knowledge-bases', json={'name': name, **extra}); assert r.status_code == 201, r.text
    return r.json()['id']


def put(client, kb, text='นโยบายเบิกจ่าย ต้องมีใบเสร็จ', name='a.txt'):
    return client.post('/api/documents', data={'knowledge_base_id': kb}, files={'file': (name, text.encode(), 'text/plain')})


# ---------- ownership and RBAC ----------

def test_a_department_admin_creates_a_knowledge_base_owned_by_their_department(client, two_departments):
    login(client, 'h@dept.test')
    kb = make_kb(client, 'นโยบาย HR')
    row = next(k for k in client.get('/api/knowledge-bases').json() if k['id'] == kb)
    assert row['department_id'] == two_departments['HR'] and row['department'] == 'HR' and row['can_write'] is True


def test_a_department_admin_manages_documents_of_their_own_department_without_a_middleman(client, two_departments):
    login(client, 'h@dept.test'); kb = make_kb(client, 'HR docs')
    doc = put(client, kb).json()['id']
    assert client.post(f'/api/documents/{doc}/reindex').status_code == 200
    assert client.post(f'/api/documents/{doc}/versions', files={'file': ('b.txt', 'ฉบับใหม่ ลาได้สิบห้าวัน'.encode(), 'text/plain')}).status_code == 200
    assert client.delete(f'/api/documents/{doc}').status_code == 200


def test_another_departments_admin_cannot_change_documents_they_can_read(client, two_departments):
    login(client, 'h@dept.test'); kb = make_kb(client, 'HR docs'); doc = put(client, kb).json()['id']
    login(client, 'f@dept.test')
    assert any(d['id'] == doc and d['can_write'] is False for d in client.get('/api/documents').json())  # the whole organisation can read it
    assert put(client, kb, 'อื่น', 'x.txt').status_code in (403, 404)
    assert client.post(f'/api/documents/{doc}/reindex').status_code in (403, 404)
    assert client.post(f'/api/documents/{doc}/versions', files={'file': ('b.txt', b'changed', 'text/plain')}).status_code in (403, 404)
    assert client.delete(f'/api/documents/{doc}').status_code in (403, 404)
    assert client.put(f'/api/knowledge-bases/{kb}', json={'name': 'hijack'}).status_code in (403, 404)


def test_a_plain_user_cannot_add_documents_to_an_organisation_visible_knowledge_base(client, two_departments):
    login(client, 'h@dept.test'); kb = make_kb(client, 'HR docs')
    login(client, 'plain@dept.test')
    assert put(client, kb).status_code in (403, 404)


def test_only_a_super_admin_moves_a_knowledge_base_between_departments(client, two_departments):
    login(client, 'h@dept.test'); kb = make_kb(client, 'HR docs')
    assert client.put(f'/api/knowledge-bases/{kb}', json={'name': 'HR docs', 'department_id': two_departments['Finance']}).status_code in (403, 404, 422)
    as_super(client)
    assert client.put(f'/api/knowledge-bases/{kb}', json={'name': 'HR docs', 'department_id': two_departments['Finance']}).status_code == 200
    login(client, 'f@dept.test'); assert put(client, kb).status_code == 201  # now Finance's
    assert client.put(f'/api/knowledge-bases/{kb}', json={'name': 'HR docs', 'department_id': 'nope'}).status_code in (403, 404, 422)


def test_a_super_admin_can_create_a_knowledge_base_for_any_department_but_only_a_real_one(client, two_departments):
    as_super(client)
    kb = make_kb(client, 'Finance docs', department_id=two_departments['Finance'])
    login(client, 'f@dept.test'); assert put(client, kb).status_code == 201
    as_super(client)
    assert client.post('/api/knowledge-bases', json={'name': 'x', 'department_id': 'nope'}).status_code == 422


def test_a_restricted_department_knowledge_base_is_readable_by_department_members_only(client, two_departments):
    login(client, 'h@dept.test'); kb = make_kb(client, 'HR private'); doc = put(client, kb).json()['id']
    assert client.put(f'/api/knowledge-bases/{kb}/access', json={'visibility': 'restricted'}).status_code == 200
    login(client, 'hm@dept.test'); assert any(d['id'] == doc for d in client.get('/api/documents').json())
    login(client, 'plain@dept.test'); assert not any(d['id'] == doc for d in client.get('/api/documents').json())
    login(client, 'f@dept.test'); assert not any(d['id'] == doc for d in client.get('/api/documents').json())


def test_a_new_document_is_searchable_as_soon_as_it_is_ready(client, two_departments):
    login(client, 'h@dept.test'); kb = make_kb(client, 'HR docs')
    doc = put(client, kb, 'สวัสดิการค่าเดินทาง จ่ายเดือนละสองพันบาท').json()['id']
    assert next(d for d in client.get('/api/documents').json() if d['id'] == doc)['status'] == 'ready'
    login(client, 'hm@dept.test')
    answer = client.post('/api/chat', json={'question': 'สวัสดิการค่าเดินทางเท่าไร', 'knowledge_base_id': kb})
    assert answer.status_code == 200 and 'สองพันบาท' in answer.text


# ---------- automatic sync ----------

class Source:
    """A stand-in for the remote file: the test decides what it serves."""
    def __init__(self): self.body = 'ระเบียบเดิม ลาได้สิบวัน'.encode(); self.calls = 0
    def __call__(self, url):
        self.calls += 1; return 'policy.txt', self.body


@pytest.fixture
def remote(monkeypatch):
    from hub import sync
    src = Source(); monkeypatch.setattr(sync, 'fetch', src); return src


def add_source(client, kb, **extra):
    return client.post(f'/api/knowledge-bases/{kb}/sources', json={'url': 'https://example.org/policy.txt', **extra})


def docs_of(kb):
    with SessionLocal() as db: return list(db.scalars(select(Document).where(Document.knowledge_base_id == kb)))


def test_a_source_creates_the_document_and_resyncs_it_as_a_new_version_only_when_the_file_changed(client, two_departments, remote):
    login(client, 'h@dept.test'); kb = make_kb(client, 'HR docs')
    sid = add_source(client, kb).json()['id']
    first = client.post(f'/api/knowledge-bases/{kb}/sources/{sid}/sync').json()
    assert first['status'] == 'updated' and [d.version for d in docs_of(kb)] == [1]
    assert client.post(f'/api/knowledge-bases/{kb}/sources/{sid}/sync').json()['status'] == 'unchanged'
    assert [d.version for d in docs_of(kb)] == [1]
    remote.body = 'ระเบียบใหม่ ลาได้สิบห้าวัน'.encode()
    assert client.post(f'/api/knowledge-bases/{kb}/sources/{sid}/sync').json()['status'] == 'updated'
    doc = docs_of(kb)
    assert len(doc) == 1 and doc[0].version == 2 and doc[0].status == 'ready'
    answer = client.post('/api/chat', json={'question': 'ลาได้กี่วัน', 'knowledge_base_id': kb})
    assert 'สิบห้าวัน' in answer.text


def test_due_sources_sync_by_themselves_and_failures_are_recorded_not_raised(client, two_departments, remote):
    from hub import sync
    login(client, 'h@dept.test'); kb = make_kb(client, 'HR docs')
    sid = add_source(client, kb, interval_minutes=60).json()['id']
    assert sync.run_due() == 1 and remote.calls == 1
    assert sync.run_due() == 0  # not due again for an hour
    remote.body = b''
    def broken(url): raise RuntimeError('เชื่อมต่อไม่ได้')
    from unittest import mock
    with mock.patch.object(sync, 'fetch', broken):
        with SessionLocal() as db:
            from hub.sync_models import KBSource
            s = db.get(KBSource, sid); s.last_checked = ''; db.commit()
        assert sync.run_due() == 1
    row = next(s for s in client.get(f'/api/knowledge-bases/{kb}/sources').json() if s['id'] == sid)
    assert row['last_status'] == 'error' and 'เชื่อมต่อไม่ได้' in row['last_error']


def test_only_the_owning_department_manages_its_sources(client, two_departments, remote):
    login(client, 'h@dept.test'); kb = make_kb(client, 'HR docs'); sid = add_source(client, kb).json()['id']
    login(client, 'f@dept.test')
    assert add_source(client, kb).status_code in (403, 404)
    assert client.post(f'/api/knowledge-bases/{kb}/sources/{sid}/sync').status_code in (403, 404)
    assert client.delete(f'/api/knowledge-bases/{kb}/sources/{sid}').status_code in (403, 404)
    login(client, 'plain@dept.test'); assert client.get(f'/api/knowledge-bases/{kb}/sources').status_code in (403, 404)


@pytest.mark.parametrize('url', ['http://example.org/a.txt', 'https://127.0.0.1/a.txt', 'https://localhost/a.txt', 'https://10.0.0.5/a.txt', 'https://169.254.169.254/latest', 'ftp://example.org/a.txt', 'https://user:pw@example.org/a.txt'])
def test_a_source_cannot_point_inside_the_network(client, two_departments, url):
    login(client, 'h@dept.test'); kb = make_kb(client, 'HR docs')
    assert client.post(f'/api/knowledge-bases/{kb}/sources', json={'url': url}).status_code == 422


def test_deleting_a_source_keeps_the_document(client, two_departments, remote):
    login(client, 'h@dept.test'); kb = make_kb(client, 'HR docs'); sid = add_source(client, kb).json()['id']
    client.post(f'/api/knowledge-bases/{kb}/sources/{sid}/sync')
    assert client.delete(f'/api/knowledge-bases/{kb}/sources/{sid}').status_code == 200
    assert len(docs_of(kb)) == 1 and client.get(f'/api/knowledge-bases/{kb}/sources').json() == []
