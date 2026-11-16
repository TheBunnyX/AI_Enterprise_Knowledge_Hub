"""Who sees which spending, and the organisation's web-search policy."""
import json
from sqlalchemy import select
from conftest import login_as
from hub import websearch
from hub.database import SessionLocal
from hub.models import Usage, User
from test_platform import upload
from test_agent_pause import scripted, events, SEARCH
from test_agent_graph import calls, answer


def usage(email, cost):
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == email))
        db.add(Usage(tenant_id=u.tenant_id, user_id=u.id, model='m', cost=cost, input_tokens=10, output_tokens=5, estimated=False)); db.commit()


def spend():
    usage('admin@local.test', 5.0); usage('member@local.test', 1.0); usage('department@local.test', 2.0)


def as_role(client, role):
    client.post('/api/auth/logout'); assert login_as(client, role).status_code == 200
    return client


# ---------- 1. spending is shown by role ----------

def test_a_user_sees_only_their_own_usage(client):
    spend()
    data = as_role(client, 'member').get('/api/analytics').json()
    assert data['scope'] == 'self' and data['requests'] == 1 and data['cost'] == 1.0
    assert [u['cost'] for u in data['top_users']] == [1.0]


def test_a_department_admin_sees_their_department(client):
    spend()  # the seeded department holds the department admin and the member; the super admin is outside it
    data = as_role(client, 'department').get('/api/analytics').json()
    assert data['scope'] == 'department' and data['requests'] == 2 and data['cost'] == 3.0


def test_a_super_admin_sees_the_organisation(client):
    spend()
    data = as_role(client, 'admin').get('/api/analytics').json()
    assert data['scope'] == 'organization' and data['cost'] == 8.0


def test_usage_export_follows_the_same_scope(client):
    spend()
    rows = lambda c: len(c.get('/api/usage/export').text.strip().splitlines()) - 1
    assert rows(as_role(client, 'member')) == 1 and rows(as_role(client, 'department')) == 2 and rows(as_role(client, 'admin')) == 3


def test_billing_summary_shows_a_user_their_own_spend_but_still_reports_an_exhausted_organisation_budget(client):
    spend()
    admin = as_role(client, 'admin')
    org = admin.get('/api/admin/organizations').json()[0]['id']
    policy = admin.get(f'/api/admin/organizations/{org}/policy').json()
    assert admin.put(f'/api/admin/organizations/{org}/policy', json={**policy, 'monthly_budget': 6}).status_code == 200
    assert admin.get('/api/billing/summary').json()['spent'] == 8.0
    mine = as_role(client, 'member').get('/api/billing/summary').json()
    assert mine['spent'] == 1.0 and mine['budget'] == 0 and mine['budget_exceeded'] is True  # blocked because the organisation is out of budget, without showing its numbers


def test_document_counts_follow_what_the_user_may_read(client):
    admin = as_role(client, 'admin')
    secret = admin.post('/api/knowledge-bases', json={'name': 'ลับ'}).json()['id']
    upload(admin, 'เอกสารลับของผู้บริหาร', kb=secret, name='secret.txt')
    everyone = admin.get('/api/analytics').json()['documents']
    assert admin.put(f'/api/knowledge-bases/{secret}/access', json={'visibility': 'restricted', 'readers': [], 'writers': []}).status_code == 200
    assert as_role(client, 'member').get('/api/analytics').json()['documents'] == everyone - 1


# ---------- 2. the organisation decides about web search ----------

def set_web_policy(client, value):
    admin = as_role(client, 'admin')
    return admin.put('/api/savings/policy', json={**admin.get('/api/savings/policy').json(), 'web_search': value})


def record_searches(monkeypatch):
    searched = []
    async def fake(query, n=5): searched.append(query); return []
    monkeypatch.setattr(websearch, 'search', fake)
    return searched


def test_web_search_policy_defaults_to_ask_and_is_visible_to_users(member):
    assert member.get('/api/savings/status').json()['web_search'] == 'ask'


def test_web_search_policy_rejects_unknown_values(client):
    assert set_web_policy(client, 'sometimes').status_code == 422


def test_when_web_search_is_off_nothing_is_searched_even_if_the_user_switches_it_on(client, monkeypatch):
    assert set_web_policy(client, 'off').status_code == 200
    searched = record_searches(monkeypatch)
    sent = scripted(monkeypatch, calls(SEARCH), answer('ตอบโดยไม่ค้นเว็บ'))
    member = as_role(client, 'member')
    assert member.get('/api/savings/status').json()['web_search'] == 'off'
    member.post('/api/chat', json={'question': 'ราคาทองวันนี้', 'web_search': True, 'use_documents': False})
    member.post('/api/chat', json={'question': 'ราคาทองวันนี้', 'web_search': True, 'agent': True})
    assert not searched
    assert all('web_search' not in json.dumps(body.get('tools', [])) for body in sent)  # the model is not even offered the tool


def test_when_web_search_is_always_allowed_the_agent_does_not_ask(client, monkeypatch):
    assert set_web_policy(client, 'always').status_code == 200
    searched = record_searches(monkeypatch)
    scripted(monkeypatch, calls(SEARCH), answer('ตอบหลังค้นเว็บ'))
    out = events(as_role(client, 'member').post('/api/chat', json={'question': 'ราคาทองวันนี้', 'agent': True}))
    assert searched == ['ราคาทองคำวันนี้'] and not any(e['type'] == 'pending' for e in out)


def test_turning_web_search_off_denies_a_run_that_was_waiting_for_approval(client, monkeypatch):
    searched = record_searches(monkeypatch)
    scripted(monkeypatch, calls(SEARCH), answer('ตอบโดยไม่ค้นเว็บ'))
    member = as_role(client, 'member')
    conversation = events(member.post('/api/chat', json={'question': 'ราคาทองวันนี้', 'agent': True}))[0]['conversation_id']
    assert set_web_policy(client, 'off').status_code == 200
    out = events(as_role(client, 'member').post('/api/chat', json={'question': 'อนุญาต', 'agent': True, 'conversation_id': conversation, 'agent_decision': 'approve'}))
    assert not searched and any(e['type'] == 'done' for e in out)
