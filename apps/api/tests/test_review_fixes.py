"""Regression tests for the review findings: audit privacy, ingest retries, chat admission, search scaling/ACL, list cost and cleanup."""
import asyncio, json, math, os, time
from collections import Counter
import pytest
from sqlalchemy import event, select
from conftest import login_as
from test_platform import upload
from hub.database import SessionLocal, DATA
from hub.models import Audit, Chunk, Document, LoginSession, User
from hub.ops_models import TaskRun, SystemAlert
from hub import jobs, retrieval, embeddings, chat_service, routes


# ---------- 1. audit log privacy ----------

def test_renaming_to_another_users_name_does_not_expose_their_audit_rows(client):
    assert login_as(client, 'admin').status_code == 200
    admin_name = client.get('/api/auth/me').json()['name']
    assert client.post('/api/knowledge-bases', json={'name': 'SECRET-KB-PROJECT-X'}).status_code == 201
    client.post('/api/auth/logout')
    assert login_as(client, 'member').status_code == 200
    assert client.put('/api/account/preferences', json={'name': admin_name, 'default_model': '', 'notifications': True}).status_code == 200
    assert 'SECRET-KB-PROJECT-X' not in json.dumps(client.get('/api/audit').json(), ensure_ascii=False)
    assert 'SECRET-KB-PROJECT-X' not in client.get('/api/audit/export?format=json').text


def test_user_keeps_own_audit_rows_after_renaming(department):
    member = department  # a department admin: members may read documents but not add them
    upload(member, 'เอกสารของฉันก่อนเปลี่ยนชื่อ', name='mine.txt')
    assert member.put('/api/account/preferences', json={'name': 'ชื่อใหม่ ไม่ซ้ำใคร', 'default_model': '', 'notifications': True}).status_code == 200
    assert 'mine.txt' in json.dumps(member.get('/api/audit').json(), ensure_ascii=False)


def test_every_audit_row_written_by_a_request_records_the_user_id(member):
    me = member.get('/api/auth/me').json()
    upload(member, 'บันทึกผู้กระทำ', name='who.txt')
    member.post('/api/chat', json={'question': 'บันทึกผู้กระทำ'})
    with SessionLocal() as db:
        rows = list(db.scalars(select(Audit).where(Audit.actor == me['name'])))
    assert rows and all(r.user_id == me['id'] for r in rows)


# ---------- 4. ingest failures reach the task queue ----------

def test_failed_ingest_marks_the_task_failed_and_raises_an_alert(admin, monkeypatch):
    def broken(name, data): raise ValueError('ไฟล์เสีย')
    monkeypatch.setattr(retrieval, 'parse', broken)
    doc = upload(admin, 'เอกสารที่อ่านไม่ได้', name='broken.txt').json()['id']
    with SessionLocal() as db:
        run = db.scalar(select(TaskRun).where(TaskRun.target_id == doc))
        assert db.get(Document, doc).status == 'failed'
        assert run.status == 'failed'
        assert db.scalar(select(SystemAlert).where(SystemAlert.alert_key == 'job:' + run.id)).status == 'active'


def test_transient_ingest_failure_is_retried_when_a_queue_is_available(admin, monkeypatch):
    monkeypatch.setenv('CELERY_BROKER_URL', 'redis://queue.test/0')
    monkeypatch.setattr(jobs, 'maintenance', lambda: None)
    queued = []; monkeypatch.setattr(jobs, 'enqueue', queued.append)
    real = embeddings.batch
    def down(*a, **k): raise ConnectionError('vector service unreachable')
    monkeypatch.setattr(embeddings, 'batch', down)
    doc = upload(admin, 'เอกสารที่รอบริการเวกเตอร์', name='later.txt').json()['id']
    assert len(queued) == 1
    jobs.execute(queued[0])
    with SessionLocal() as db:
        run = db.get(TaskRun, queued[0])
        assert run.status == 'retry_wait'
        assert db.get(Document, doc).status == 'processing'  # not shown as failed while a retry is pending
        run.next_attempt = 0; db.commit()
    monkeypatch.setattr(embeddings, 'batch', real)
    jobs.execute(queued[0])
    with SessionLocal() as db:
        assert db.get(TaskRun, queued[0]).status == 'completed'
        assert db.get(Document, doc).status == 'ready'


# ---------- 3. chat admission ----------

def _spy_search(monkeypatch, seen):
    real = chat_service.search
    def spy(*a, **k):
        try: asyncio.get_running_loop(); seen['on_event_loop'] = True
        except RuntimeError: seen['on_event_loop'] = False
        seen['lock_already_taken'] = seen.get('locks', 0) > 0
        return real(*a, **k)
    monkeypatch.setattr(chat_service, 'search', spy)


def test_chat_retrieval_does_not_run_on_the_event_loop(member, monkeypatch):
    upload(member)
    seen = {}; _spy_search(monkeypatch, seen)
    assert member.post('/api/chat', json={'question': 'ลาพักร้อน'}).status_code == 200
    assert seen['on_event_loop'] is False


def test_chat_takes_the_tenant_lock_only_after_retrieval(member, monkeypatch):
    upload(member)
    seen = {}; _spy_search(monkeypatch, seen)
    def watch(state):
        if getattr(state.statement, '_for_update_arg', None) is not None: seen['locks'] = seen.get('locks', 0) + 1
    event.listen(SessionLocal, 'do_orm_execute', watch)
    try: assert member.post('/api/chat', json={'question': 'ลาพักร้อน'}).status_code == 200
    finally: event.remove(SessionLocal, 'do_orm_execute', watch)
    assert seen['lock_already_taken'] is False
    assert seen['locks'] >= 1  # admission is still serialized per tenant


# ---------- search: same ranking, lighter work ----------

def _reference_search(db, tenant_id, query, mode='hybrid', limit=10):
    """The original scoring, kept here to pin the ranking: BM25 over tone-insensitive trigrams + cosine, fused by reciprocal rank."""
    rows = list(db.execute(select(Chunk, Document).join(Document, Chunk.document_id == Document.id).where(Chunk.tenant_id == tenant_id, Document.status == 'ready', Chunk.embedding_version == embeddings.specification()['version'])))
    q = Counter(retrieval.lexical_tokens(query)); qv = embeddings.batch([query], tenant_id, 'query')[0]
    corpus = [Counter(retrieval.lexical_tokens(c.text + ' ' + d.name)) for c, d in rows]
    average = sum(sum(t.values()) for t in corpus) / (len(corpus) or 1) or 1
    frequencies = Counter(t for ct in corpus for t in ct)
    sparse = []; dense = []
    for (c, d), ct in zip(rows, corpus):
        lexical = 0.
        for t in q:
            tf = ct[t]; idf = math.log(1 + (len(rows) - frequencies[t] + .5) / (frequencies[t] + .5))
            lexical += idf * (tf * 2.2) / (tf + 1.2 * (.25 + .75 * sum(ct.values()) / average)) if tf else 0
        sparse.append((lexical, c)); dense.append((sum(a * b for a, b in zip(qv, c.embedding)), c))
    sparse.sort(key=lambda x: x[0], reverse=True); dense.sort(key=lambda x: x[0], reverse=True)
    ranks = {}
    for source in ([sparse] if mode == 'keyword' else [dense] if mode == 'semantic' else [sparse, dense]):
        for rank, (score, c) in enumerate(source):
            if score < (0.10 if source is sparse else 0.16): continue
            ranks[c.id] = ranks.get(c.id, 0) + 1 / (60 + rank + 1)
    return [(id, round(s, 5)) for id, s in sorted(ranks.items(), key=lambda x: x[1], reverse=True)[:limit]]


@pytest.mark.parametrize('mode', ['hybrid', 'keyword', 'semantic'])
def test_search_ranking_is_unchanged(admin, mode):
    for i, text in enumerate(['นโยบายลาพักร้อน พนักงานลาได้สิบวันต่อปี ต้องแจ้งล่วงหน้า', 'ระเบียบการเบิกค่าเดินทาง ต้องแนบใบเสร็จทุกครั้ง', 'การลาป่วยต้องมีใบรับรองแพทย์เมื่อลาเกินสามวัน', 'Travel expenses are reimbursed within thirty days']):
        assert upload(admin, text, name=f'rank-{i}.txt').status_code == 201
    tenant = admin.get('/api/auth/me').json()['tenant_id']
    for query in ('ลาพักร้อนได้กี่วัน', 'ใบเสร็จค่าเดินทาง', 'travel expenses', 'ลาป่วย ใบรับรองแพทย์'):
        with SessionLocal() as db:
            expected = _reference_search(db, tenant, query, mode)
            got = [(r['chunk_id'], r['score']) for r in retrieval.search(db, tenant, query, mode=mode)]
        assert sorted(got) == sorted(expected) and [s for _, s in got] == [s for _, s in expected], query


def test_keyword_search_works_while_the_embedding_service_is_down(admin, monkeypatch):
    upload(admin, 'ระเบียบการเบิกค่าเดินทาง ต้องแนบใบเสร็จ', name='keyword.txt')
    def down(*a, **k): raise ConnectionError('embedding service unreachable')
    monkeypatch.setattr(embeddings, 'batch', down)
    found = admin.get('/api/search', params={'q': 'เบิกค่าเดินทาง', 'mode': 'keyword'})
    assert found.status_code == 200 and any(r['name'] == 'keyword.txt' for r in found.json())


# ---------- search: the vector store filters by what the user may read ----------

@pytest.fixture
def vector_store(monkeypatch):
    import qdrant_client
    shared = qdrant_client.QdrantClient(':memory:')
    monkeypatch.setattr(qdrant_client, 'QdrantClient', lambda *a, **k: shared)
    monkeypatch.setenv('QDRANT_URL', 'http://vectors.test')
    return shared


def test_dense_search_finds_readable_documents_behind_many_closer_unreadable_ones(client, vector_store):
    assert login_as(client, 'admin').status_code == 200
    phrase = 'แผนปรับโครงสร้างเงินเดือนประจำปี '
    secret = client.post('/api/knowledge-bases', json={'name': 'ลับเฉพาะผู้บริหาร'}).json()['id']
    assert upload(client, phrase * 1400, kb=secret, name='secret.txt').status_code == 201  # ~60 chunks, all closer to the query
    assert client.put(f'/api/knowledge-bases/{secret}/access', json={'visibility': 'restricted', 'readers': [], 'writers': []}).status_code == 200
    assert upload(client, phrase + 'ฉบับเผยแพร่สำหรับพนักงานทุกคน', name='public.txt').status_code == 201
    with SessionLocal() as db:
        assert db.scalar(select(Chunk.id).join(Document, Document.id == Chunk.document_id).where(Document.name == 'secret.txt').offset(50)) is not None
    client.post('/api/auth/logout')
    assert login_as(client, 'member').status_code == 200
    names = [r['name'] for r in client.get('/api/search', params={'q': phrase.strip(), 'mode': 'semantic'}).json()]
    assert 'secret.txt' not in names
    assert 'public.txt' in names


def test_search_with_a_vector_store_does_not_read_stored_embeddings(admin, vector_store):
    upload(admin, 'คู่มือการใช้งานระบบจองห้องประชุม', name='rooms.txt')
    tenant = admin.get('/api/auth/me').json()['tenant_id']
    loaded = []
    def watch(state):
        if state.is_select and any(getattr(c, 'key', '') == 'embedding' and getattr(getattr(c, 'table', None), 'name', '') == 'document_chunks' for c in state.statement.selected_columns): loaded.append(1)
    event.listen(SessionLocal, 'do_orm_execute', watch)
    try:
        with SessionLocal() as db: found = retrieval.search(db, tenant, 'จองห้องประชุม')
    finally: event.remove(SessionLocal, 'do_orm_execute', watch)
    assert any(r['name'] == 'rooms.txt' for r in found)
    assert not loaded


# ---------- list endpoints compute permissions once ----------

def _count_acl(monkeypatch):
    calls = []; real = routes.visible_documents
    def counted(*a, **k): calls.append(1); return real(*a, **k)
    monkeypatch.setattr(routes, 'visible_documents', counted)
    return calls


def test_document_list_resolves_permissions_a_fixed_number_of_times(admin, monkeypatch):
    for i in range(4): upload(admin, f'เอกสารลำดับที่ {i}', name=f'n-{i}.txt')
    calls = _count_acl(monkeypatch)
    docs = admin.get('/api/documents').json()
    assert len(docs) >= 4 and all(d['can_write'] for d in docs)
    assert len(calls) <= 2


def test_knowledge_base_list_resolves_permissions_once(admin, monkeypatch):
    for i in range(3): admin.post('/api/knowledge-bases', json={'name': f'คลัง {i}'})
    upload(admin, 'เอกสารสำหรับนับ', name='count.txt')
    calls = _count_acl(monkeypatch)
    bases = admin.get('/api/knowledge-bases').json()
    assert len(bases) >= 4 and sum(b['documents'] for b in bases) >= 1
    assert len(calls) <= 1


# ---------- cleanup ----------

def test_cleanup_removes_expired_sessions_stale_attachments_and_expired_generated_files(member):
    from hub import cleanup, storage
    from hub.generated import GeneratedFile
    me = member.get('/api/auth/me').json()
    old = member.post('/api/chat/attachments', files={'file': ('old.txt', 'ไฟล์แนบเก่า'.encode(), 'text/plain')}).json()['id']
    new = member.post('/api/chat/attachments', files={'file': ('new.txt', 'ไฟล์แนบใหม่'.encode(), 'text/plain')}).json()['id']
    folder = DATA / 'files' / me['tenant_id'] / 'chat-attachments' / me['id']
    two_days_ago = time.time() - 2 * 86400; os.utime(folder / old, (two_days_ago, two_days_ago))
    with SessionLocal() as db:
        db.add(LoginSession(user_id=me['id'], token_hash='expired-session', expires=time.time() - 60))
        storage.put('gen-expired', b'x'); storage.put('gen-live', b'x')
        db.add(GeneratedFile(tenant_id=me['tenant_id'], user_id=me['id'], name='old.csv', kind='csv', size=1, storage_key='gen-expired', expires_at='2000-01-01T00:00:00+00:00'))
        db.add(GeneratedFile(tenant_id=me['tenant_id'], user_id=me['id'], name='live.csv', kind='csv', size=1, storage_key='gen-live', expires_at='2999-01-01T00:00:00+00:00'))
        db.commit()
    done = cleanup.run()
    assert done == {'sessions': 1, 'attachments': 1, 'generated_files': 1, 'agent_runs': 0}
    assert not (folder / old).exists() and (folder / new).exists()
    assert not (DATA / 'files' / 'gen-expired').exists() and (DATA / 'files' / 'gen-live').exists()
    with SessionLocal() as db:
        assert db.scalar(select(LoginSession).where(LoginSession.token_hash == 'expired-session')) is None
        assert [f.name for f in db.scalars(select(GeneratedFile))] == ['live.csv']
    assert member.get('/api/auth/me').status_code == 200  # the live session survives
