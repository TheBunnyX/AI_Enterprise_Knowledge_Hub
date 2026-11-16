import asyncio
from datetime import timedelta
from sqlalchemy import select
from hub import savings, embeddings, gateway
from hub.database import SessionLocal
from hub.models import User, Usage, AIModel
from hub.feature_models import GenerationJob
from hub.savings_models import AnswerCache, EmbeddingCache, SavingsEvent
from test_team import login, tenant_of, seed_people, PW

def put_policy(client, **over):
    base = {k: v for k, v in savings.DEFAULTS.items()}
    return client.put('/api/savings/policy', json=base | over)

def test_policy_is_admin_only_and_validated(admin):
    assert admin.get('/api/savings/policy').json()['router_model'] == 'respan/span-01-lite:free'
    assert put_policy(admin, max_output_tokens=10).status_code == 422
    r = put_policy(admin, auto_route=True, rate_per_minute=5)
    assert r.status_code == 200 and r.json()['auto_route'] is True
    assert admin.get('/api/savings/status').json()['auto_route'] is True
    t = tenant_of('admin@local.test'); seed_people(t)
    login(admin, 'd@team.test')
    assert admin.get('/api/savings/policy').status_code == 403
    assert admin.put('/api/savings/policy', json=savings.DEFAULTS).status_code == 403
    assert admin.get('/api/savings/status').status_code == 200  # members read only the flags they need

def test_answer_cache_key_expiry_and_scope(client):
    k1 = savings.answer_key('t', '  สวัสดี  ครับ ', ['c1', 'c2'], 1024)
    assert k1 == savings.answer_key('t', 'สวัสดี ครับ', ['c1', 'c2'], 1024)
    assert k1 != savings.answer_key('t', 'สวัสดี ครับ', ['c1'], 1024)      # different evidence (permissions or documents changed)
    assert k1 != savings.answer_key('u', 'สวัสดี ครับ', ['c1', 'c2'], 1024)  # other organisation
    savings.cache_store('t', k1, 'q', 'a', [{'n': 1}], 'GPT', 0.02, 7)
    with SessionLocal() as db:
        assert savings.cache_lookup(db, k1).answer == 'a'
        e = db.scalar(select(AnswerCache)); e.expires_at = (savings.utc_now() - timedelta(days=1)).isoformat(); db.commit()
        assert savings.cache_lookup(db, k1) is None
        savings.purge_expired(db)
        assert db.scalar(select(AnswerCache)) is None

def test_embedding_cache_only_fetches_missing(client, monkeypatch):
    monkeypatch.setenv('EMBEDDING_MODEL', 'm'); monkeypatch.setenv('EMBEDDING_DIMENSIONS', '3'); monkeypatch.setenv('EMBEDDING_BATCH_SIZE', '8')
    monkeypatch.setattr(gateway, 'configuration', lambda db=None, provider='': ('http://gateway.test', 'k'))
    calls = []
    def fake(texts, spec, url, key):
        calls.append(list(texts)); return [[float(len(t)), 0.0, 1.0] for t in texts]
    monkeypatch.setattr(embeddings, '_fetch', fake)
    a = embeddings.batch(['aa', 'bbb'], 'ten')
    b = embeddings.batch(['bbb', 'aa', 'cccc'], 'ten')
    assert calls == [['aa', 'bbb'], ['cccc']] and b[0] == a[1] and b[1] == a[0] and b[2][0] == 4.0
    embeddings.batch(['aa'], 'other')                                       # other organisation does not reuse it
    assert calls[-1] == ['aa']
    with SessionLocal() as db:
        assert db.scalar(select(EmbeddingCache).limit(1)) is not None
        assert db.scalar(select(SavingsEvent).where(SavingsEvent.kind == 'embedding_hit')) is not None

def test_prompt_cache_marks_stable_prefix_for_claude_only():
    msgs = [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'h'}, {'role': 'assistant', 'content': 'a'}, {'role': 'user', 'content': 'q'}]
    out = savings.apply_prompt_cache(msgs, 'anthropic/claude-sonnet')
    assert out[0]['content'][0]['cache_control'] == {'type': 'ephemeral'} and out[2]['content'][0]['cache_control']
    assert out[3]['content'] == 'q' and msgs[0]['content'] == 's'
    assert savings.apply_prompt_cache(msgs, 'openai/gpt') is msgs

def test_router_picks_allowed_model_and_survives_failure(client, monkeypatch):
    monkeypatch.setattr(gateway, 'configuration', lambda db=None, provider='': ('http://gateway.test', 'k'))
    with SessionLocal() as db:
        cheap = AIModel(name='small', provider='X', api_id='x/small', input_price=0.1, output_price=0.2)
        big = AIModel(name='big', provider='X', api_id='x/big', input_price=5, output_price=15)
        db.add_all([cheap, big]); db.commit(); db.refresh(cheap); db.refresh(big)
        reply = {'text': ''}
        class Resp:
            def raise_for_status(self): pass
            def json(self): return {'choices': [{'message': {'content': reply['text']}}]}
        class Client:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, headers=None, json=None):
                assert json['model'] == 'respan/span-01-lite:free' and '| big |' in json['messages'][1]['content']
                if reply['text'] == 'boom': raise savings.httpx.ConnectError('down')
                return Resp()
        monkeypatch.setattr(savings.httpx, 'AsyncClient', Client)
        run = lambda: asyncio.run(savings.route_model(db, 'q', 100, [cheap, big], 'respan/span-01-lite:free'))
        reply['text'] = f'ใช้ {cheap.id}'; assert run().id == cheap.id
        reply['text'] = 'x/big'; assert run().id == big.id
        reply['text'] = 'something else'; assert run() is None
        reply['text'] = 'boom'; assert run() is None
        assert asyncio.run(savings.route_model(db, 'q', 1, [cheap], 'r')) is None  # nothing to choose between

def test_rate_limits_apply_to_requests(admin):
    t = tenant_of('admin@local.test')
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == 'admin@local.test'))
        db.add_all([Usage(tenant_id=t, user_id=u.id, model='m') for _ in range(2)]); db.commit()
    assert put_policy(admin, rate_per_minute=2).status_code == 200
    r = admin.post('/api/chat', json={'question': 'hello'})
    assert r.status_code == 429 and 'ต่อนาที' in r.json()['detail']
    put_policy(admin, rate_per_minute=0, daily_requests=2)
    r = admin.post('/api/chat', json={'question': 'hello'})
    assert r.status_code == 429 and 'ต่อวัน' in r.json()['detail']
    put_policy(admin, rate_per_minute=0, daily_requests=0)
    assert admin.post('/api/chat', json={'question': 'hello'}).status_code != 429

def test_budget_alert_published_at_threshold(admin):
    from hub.ops_models import SystemAlert
    t = tenant_of('admin@local.test')
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == 'admin@local.test')); u.monthly_budget = 10; db.add(Usage(tenant_id=t, user_id=u.id, model='m', cost=8.5)); db.commit(); uid = u.id
    savings.check_budget_alerts(t, uid)
    with SessionLocal() as db:
        a = db.scalar(select(SystemAlert).where(SystemAlert.alert_key.like('user-budget:%')))
        assert a and a.tenant_id == t and '85%' in a.title and a.severity == 'warning'

def test_media_estimate_approval_and_daily_limit(admin, monkeypatch):
    t = tenant_of('admin@local.test')
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == 'admin@local.test'))
        m = AIModel(name='vid', provider='X', api_id='x/video', category='Video', enabled=True); db.add(m); db.flush()
        for cost in (0.4, 0.6):
            db.add(GenerationJob(tenant_id=t, user_id=u.id, model_id=m.id, kind='video', status='completed', cost=cost, cost_known=True))
        db.commit(); mid = m.id
    assert admin.get(f'/api/media/estimate?model_id={mid}').json()['cost'] == 0.5
    put_policy(admin, media_approval_usd=0.5, media_daily_limit=3)
    est = admin.get(f'/api/media/estimate?model_id={mid}').json()
    assert est['needs_approval'] and est['remaining_today'] == 1
    monkeypatch.setattr(gateway, 'configured', lambda db=None, provider='': True)
    import hub.jobs as jobs
    scheduled = []
    monkeypatch.setattr(jobs, 'schedule_media', lambda id, bg: scheduled.append(id))
    r = admin.post('/api/media/jobs', data={'kind': 'video', 'model_id': mid, 'prompt': 'ทะเล', 'options': '{}'})
    assert r.status_code == 202 and r.json()['status'] == 'awaiting_approval' and not scheduled
    pending = admin.get('/api/media/approvals').json()
    assert len(pending) == 1 and pending[0]['estimate'] == 0.5
    assert admin.post(f"/api/media/jobs/{pending[0]['id']}/approve").status_code == 200
    assert scheduled == [pending[0]['id']] and admin.get('/api/media/approvals').json() == []
    assert admin.post(f"/api/media/jobs/{pending[0]['id']}/approve").status_code == 404
    put_policy(admin, media_approval_usd=0, media_daily_limit=3)  # 3 jobs created today already (2 history + 1 new)
    r = admin.post('/api/media/jobs', data={'kind': 'video', 'model_id': mid, 'prompt': 'ภูเขา', 'options': '{}'})
    assert r.status_code == 429 and 'ต่อวัน' in r.json()['detail']

def test_report_breaks_down_spend_and_savings(admin):
    t = tenant_of('admin@local.test'); p = seed_people(t)
    with SessionLocal() as db:
        db.add(Usage(tenant_id=t, user_id=p['m1'], model='GPT', cost=0.3))
        db.add_all([SavingsEvent(tenant_id=t, user_id=p['m1'], kind='cache_hit', saved=0.2, detail='GPT'), SavingsEvent(tenant_id=t, user_id=p['m1'], kind='route', detail='small')])
        db.commit()
    r = admin.get('/api/savings/report?days=30').json()
    assert {m['model'] for m in r['by_model']} >= {'GPT', 'm'}
    assert r['top_users'][0]['email'] == 'm1@team.test' and r['top_users'][0]['cost'] == 0.8
    assert r['by_department'][0]['name'] == 'แผนก X'
    assert r['savings']['cache_hits'] == 1 and r['savings']['cache_saved'] == 0.2 and r['savings']['routed_to'] == {'small': 1}
    login(admin, 'm1@team.test')
    assert admin.get('/api/savings/report').status_code == 403

def test_chat_serves_cached_answer_for_free(admin, monkeypatch):
    seen = []
    real = savings.cache_lookup
    monkeypatch.setattr(savings, 'cache_lookup', lambda db, key: (seen.append(key), real(db, key))[1])
    body = {'question': 'นโยบายการทำงานแบบยืดหยุ่น ทำงานจากที่บ้านได้กี่วัน'}
    first = admin.post('/api/chat', json=body)
    assert first.status_code == 200 and seen and seen[0]
    savings.cache_store(tenant_of('admin@local.test'), seen[0], body['question'], 'คำตอบจากแคช', [{'number': 1}], 'GPT', 0.05, 7)
    second = admin.post('/api/chat', json=body)
    assert 'คำตอบจากแคช' in second.text and '"done"' in second.text
    with SessionLocal() as db:
        row = db.scalars(select(Usage).where(Usage.model.like('แคชคำตอบ%'))).first()
        assert row and row.cost == 0 and not row.estimated
        ev = db.scalar(select(SavingsEvent).where(SavingsEvent.kind == 'cache_hit'))
        assert ev.saved == 0.05 and db.scalar(select(AnswerCache)).hits == 1
    put_policy(admin, cache=False)
    assert 'คำตอบจากแคช' not in admin.post('/api/chat', json=body).text
