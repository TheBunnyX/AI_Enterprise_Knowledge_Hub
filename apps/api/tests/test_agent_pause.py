"""Agent pauses for a person (a clarifying question, or approval to search the web) and continues from saved state."""
import asyncio, json, time
import httpx
from sqlalchemy import select, func
from hub import agent, websearch
from hub.database import SessionLocal
from test_agent_graph import Model, calls, answer, tool_messages
from test_platform import upload

ASK = ('q1', 'ask_user', {'question': 'หมายถึงการลาประเภทไหน', 'options': ['ลาพักร้อน', 'ลาป่วย']})
SEARCH = ('w1', 'web_search', {'query': 'ราคาทองคำวันนี้'})


def start(model, web=False):
    pause = []
    out = asyncio.run(agent.agent_prepare(model, 'http://x', 'k', {'api_id': 'm'}, [{'role': 'user', 'content': 'q'}], 100, 0, lambda s: None,
                                          user_id='u', tenant_id='t', web=web, conversation_id='conv', pause=pause))
    return out, pause


def resume(model, pause, reply, web=False):
    again = []
    out = asyncio.run(agent.agent_prepare(model, 'http://x', 'k', {'api_id': 'm'}, [{'role': 'user', 'content': 'ignored on resume'}], 100, 0, lambda s: None,
                                          user_id='u', tenant_id='t', web=web, conversation_id='conv', pause=again, thread_id=pause[0]['thread_id'], resume=reply))
    return out, again


def stored_rows():
    from hub.agent_store import AgentRun, AgentCheckpoint, AgentWrite
    with SessionLocal() as db:
        return [db.scalar(select(func.count()).select_from(t)) for t in (AgentRun, AgentCheckpoint, AgentWrite)]


def test_a_clarifying_question_pauses_the_run(client):
    model = Model(calls(ASK), answer())
    (msgs, sources, text, tin, tout), pause = start(model)
    assert 'หมายถึงการลาประเภทไหน' in text and len(model.payloads) == 1 and (tin, tout) == (10, 2)
    assert pause[0]['kind'] == 'question' and pause[0]['options'] == ['ลาพักร้อน', 'ลาป่วย'] and pause[0]['thread_id']


def test_the_users_reply_continues_the_same_run(client):
    model = Model(calls(ASK), answer('ลาพักร้อนได้ปีละ 10 วัน'))
    _, pause = start(model)
    (msgs, _, text, tin, tout), again = resume(model, pause, {'answer': 'ลาพักร้อน'})
    assert text == 'ลาพักร้อนได้ปีละ 10 วัน' and not again
    assert 'ลาพักร้อน' in tool_messages(msgs)['q1'] and msgs[0] == {'role': 'user', 'content': 'q'}  # the original conversation, not a restart
    assert (tin, tout) == (20, 5)  # only what the second part used; the first part was metered when it paused


def test_a_paused_run_survives_a_restart(client):
    model = Model(calls(ASK), answer('ตอบหลังรีสตาร์ต'))
    _, pause = start(model)
    agent.GRAPH = agent._build(); agent.PAUSABLE = agent._build(agent.DbSaver())  # nothing kept in memory, as after a restart
    (_, _, text, _, _), _ = resume(model, pause, {'answer': 'ลาป่วย'})
    assert text == 'ตอบหลังรีสตาร์ต'


def test_a_finished_run_leaves_nothing_stored(client):
    model = Model(calls(ASK), answer())
    _, pause = start(model)
    assert stored_rows()[0] == 1 and stored_rows()[1] >= 1
    resume(model, pause, {'answer': 'ลาพักร้อน'})
    assert stored_rows() == [0, 0, 0]


def test_web_search_needs_approval_when_the_user_did_not_switch_web_on(client, monkeypatch):
    searched = []
    async def fake(query, n=5): searched.append(query); return [{'title': 'ราคาทอง', 'url': 'https://example.test/gold', 'snippet': 'บาทละ 40,000'}]
    monkeypatch.setattr(websearch, 'search', fake)
    model = Model(calls(SEARCH), answer('ทองบาทละ 40,000 [1]'))
    (_, _, text, _, _), pause = start(model)
    assert pause[0]['kind'] == 'approval' and pause[0]['queries'] == ['ราคาทองคำวันนี้'] and 'ราคาทองคำวันนี้' in text
    assert not searched  # nothing left the organisation before the user agreed
    (msgs, sources, text, _, _), _ = resume(model, pause, {'approve': True})
    assert searched == ['ราคาทองคำวันนี้'] and text == 'ทองบาทละ 40,000 [1]' and sources[0]['url'] == 'https://example.test/gold'


def test_a_denied_web_search_is_never_sent(client, monkeypatch):
    searched = []
    async def fake(query, n=5): searched.append(query); return []
    monkeypatch.setattr(websearch, 'search', fake)
    model = Model(calls(SEARCH), answer('ตอบโดยไม่ค้นเว็บ'))
    _, pause = start(model)
    (msgs, _, text, _, _), _ = resume(model, pause, {'approve': False})
    assert not searched and text == 'ตอบโดยไม่ค้นเว็บ' and 'ไม่อนุญาต' in tool_messages(msgs)['w1']


def test_web_search_runs_without_asking_when_the_user_switched_web_on(client, monkeypatch):
    async def fake(query, n=5): return []
    monkeypatch.setattr(websearch, 'search', fake)
    (_, _, text, _, _), pause = start(Model(calls(SEARCH), answer()), web=True)
    assert text == 'คำตอบสุดท้าย' and not pause


def test_expired_paused_runs_are_cleaned_up(client):
    from hub import cleanup
    from hub.agent_store import AgentRun
    _, pause = start(Model(calls(ASK), answer()))
    with SessionLocal() as db:
        db.get(AgentRun, pause[0]['thread_id']).expires = time.time() - 1; db.commit()
    assert cleanup.run()['agent_runs'] == 1 and stored_rows() == [0, 0, 0]


# ---------- through the chat API ----------

def scripted(monkeypatch, *replies):
    """Make the gateway answer with these replies in order; returns the list of request bodies it received."""
    sent = []; queue = list(replies)
    def respond(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=(queue.pop(0) if len(queue) > 1 else queue[0]).data)
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda *a, **kw: real(*a, **{**kw, 'transport': httpx.MockTransport(respond)}))
    return sent


def events(response): return [json.loads(line) for line in response.text.splitlines()]


def test_chat_shows_the_question_and_resumes_with_the_next_message(member, monkeypatch):
    sent = scripted(monkeypatch, calls(ASK), answer('ลาพักร้อนได้ปีละ 10 วัน'))
    first = events(member.post('/api/chat', json={'question': 'ลาได้กี่วัน', 'agent': True}))
    conversation = first[0]['conversation_id']
    pending = next(e for e in first if e['type'] == 'pending')
    assert pending['kind'] == 'question' and pending['options'] == ['ลาพักร้อน', 'ลาป่วย'] and 'thread_id' not in pending
    assert member.get(f'/api/conversations/{conversation}/agent-pending').json()['kind'] == 'question'
    second = events(member.post('/api/chat', json={'question': 'ลาพักร้อน', 'agent': True, 'conversation_id': conversation}))
    assert 'ลาพักร้อนได้ปีละ 10 วัน' in ''.join(e.get('text', '') for e in second if e['type'] == 'delta')
    assert len(sent) == 2 and sent[1]['messages'][-1]['role'] == 'tool' and 'ลาพักร้อน' in sent[1]['messages'][-1]['content']
    assert member.get(f'/api/conversations/{conversation}/agent-pending').json() is None


def test_chat_approval_decision_resumes_the_run(member, monkeypatch):
    searched = []
    async def fake(query, n=5): searched.append(query); return []
    monkeypatch.setattr(websearch, 'search', fake)
    scripted(monkeypatch, calls(SEARCH), answer('คำตอบหลังค้นเว็บ'))
    first = events(member.post('/api/chat', json={'question': 'ราคาทองวันนี้', 'agent': True}))
    conversation = first[0]['conversation_id']
    assert next(e for e in first if e['type'] == 'pending')['kind'] == 'approval' and not searched
    second = events(member.post('/api/chat', json={'question': 'อนุญาต', 'agent': True, 'conversation_id': conversation, 'agent_decision': 'approve'}))
    assert searched == ['ราคาทองคำวันนี้'] and 'คำตอบหลังค้นเว็บ' in ''.join(e.get('text', '') for e in second if e['type'] == 'delta')


def test_a_new_question_instead_of_a_decision_drops_the_waiting_run(member, monkeypatch):
    scripted(monkeypatch, calls(SEARCH), answer('คำตอบใหม่'))
    first = events(member.post('/api/chat', json={'question': 'ราคาทองวันนี้', 'agent': True}))
    conversation = first[0]['conversation_id']
    second = events(member.post('/api/chat', json={'question': 'ช่างมัน ถามเรื่องอื่น', 'agent': True, 'conversation_id': conversation}))
    assert any(e['type'] == 'done' for e in second)
    assert stored_rows()[0] <= 1  # the abandoned run is gone (a new pause may exist because the script asks to search again)


def test_another_user_cannot_see_or_resume_a_paused_run(client, monkeypatch):
    from conftest import login_as
    scripted(monkeypatch, calls(ASK), answer())
    login_as(client, 'member')
    conversation = events(client.post('/api/chat', json={'question': 'ลาได้กี่วัน', 'agent': True}))[0]['conversation_id']
    client.post('/api/auth/logout'); login_as(client, 'admin')
    assert client.get(f'/api/conversations/{conversation}/agent-pending').status_code == 404
