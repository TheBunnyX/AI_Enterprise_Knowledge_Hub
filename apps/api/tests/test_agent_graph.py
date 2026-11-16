"""Agent loop behaviour: every tool call is answered, calls of one round run together, and one failure does not end the answer."""
from conftest import login_as
import asyncio, json, time
import httpx
import pytest
from hub import agent
from test_platform import upload


class Reply:
    def __init__(self, data, code=200): self.data = data; self.status_code = code
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f'HTTP {self.status_code}')
    def json(self): return self.data


def calls(*items, tokens=(10, 2)):
    """A model reply asking for tools: items are (id, tool name, arguments)."""
    return Reply({'usage': {'prompt_tokens': tokens[0], 'completion_tokens': tokens[1]}, 'choices': [{'message': {'content': '', 'tool_calls': [
        {'id': id, 'function': {'name': name, 'arguments': json.dumps(args)}} for id, name, args in items]}}]})


def answer(text='คำตอบสุดท้าย'):
    return Reply({'usage': {'prompt_tokens': 20, 'completion_tokens': 5}, 'choices': [{'message': {'content': text}}]})


class Model:
    """Plays back scripted replies and records what it was sent."""
    def __init__(self, *replies): self.replies = list(replies); self.payloads = []
    async def post(self, url, headers=None, json=None):
        self.payloads.append(json)
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def run(model, **options):
    status = []
    out = asyncio.run(agent.agent_prepare(model, 'http://x', 'k', {'api_id': 'm'}, [{'role': 'user', 'content': 'q'}], 100, 0, status.append,
                                          user_id='u', tenant_id='t', web=options.get('web', False)))
    return out, status


def tool_messages(msgs): return {m['tool_call_id']: m['content'] for m in msgs if m['role'] == 'tool'}


def hit(chunk, text='ข้อความ'):
    return {'chunk_id': chunk, 'document_id': 'd-' + chunk, 'name': chunk + '.pdf', 'page': 1, 'snippet': text, 'version': 1, 'score': 1, 'knowledge_base_id': 'kb'}


def test_every_tool_call_of_a_round_gets_a_response(monkeypatch):
    monkeypatch.setattr(agent, '_fetch', lambda *a: {'found': []})
    many = [(f'call-{i}', 'search_documents', {'query': f'คำค้น {i}'}) for i in range(6)]
    (msgs, _, text, _, _), _ = run(Model(calls(*many), answer()))
    assert text == 'คำตอบสุดท้าย'
    assert set(tool_messages(msgs)) == {f'call-{i}' for i in range(6)}  # an unanswered call id makes the provider reject the next request


def test_tool_calls_of_one_round_run_at_the_same_time(monkeypatch):
    def slow(*a): time.sleep(0.4); return {'found': []}
    monkeypatch.setattr(agent, '_fetch', slow)
    three = [(f'c{i}', 'search_documents', {'query': f'q{i}'}) for i in range(3)]
    began = time.monotonic()
    (_, _, text, _, _), _ = run(Model(calls(*three), answer()))
    assert text and time.monotonic() - began < 0.9  # one after another would take 1.2 s


def test_a_failing_tool_is_reported_to_the_model_instead_of_ending_the_answer(monkeypatch):
    def broken(user_id, tenant_id, conversation_id, name, args):
        if args.get('query') == 'พัง': raise RuntimeError('database went away')
        return {'found': [hit('ok')]}
    monkeypatch.setattr(agent, '_fetch', broken)
    (msgs, sources, text, _, _), _ = run(Model(calls(('bad', 'search_documents', {'query': 'พัง'}), ('good', 'search_documents', {'query': 'ดี'})), answer()))
    replies = tool_messages(msgs)
    assert text == 'คำตอบสุดท้าย' and 'error' in replies['bad'] and 'database went away' not in replies['bad']
    assert 'ok.pdf' in replies['good'] and [s['number'] for s in sources] == [1]


def test_a_busy_model_is_retried(monkeypatch):
    monkeypatch.setattr(agent, '_fetch', lambda *a: {'found': []})
    model = Model(calls(('a', 'search_documents', {'query': 'x'})), Reply({}, 503), answer())
    (_, _, text, tin, tout), _ = run(model)
    assert text == 'คำตอบสุดท้าย' and len(model.payloads) == 3 and (tin, tout) == (30, 7)


def test_the_same_call_is_not_executed_twice(monkeypatch):
    seen = []
    monkeypatch.setattr(agent, '_fetch', lambda user_id, tenant_id, conversation_id, name, args: seen.append(args) or {'found': []})
    same = ('search_documents', {'query': 'ลาพักร้อน'})
    (msgs, _, text, _, _), _ = run(Model(calls(('first', *same)), calls(('again', *same)), answer()))
    assert text and len(seen) == 1
    assert 'ซ้ำ' in tool_messages(msgs)['again']


def test_tool_use_stops_when_the_token_budget_is_spent(monkeypatch):
    monkeypatch.setattr(agent, '_fetch', lambda *a: {'found': []})
    monkeypatch.setattr(agent, 'MAX_TOKENS', 5000)
    model = Model(calls(('a', 'search_documents', {'query': 'x'}), tokens=(9000, 100)), answer())
    (_, _, text, _, _), _ = run(model)
    assert text == 'คำตอบสุดท้าย' and 'tools' in model.payloads[0] and 'tools' not in model.payloads[1]


def test_citation_numbers_stay_in_order_and_unique_across_parallel_searches(monkeypatch):
    results = {'หนึ่ง': [hit('a'), hit('b')], 'สอง': [hit('b'), hit('c')]}
    monkeypatch.setattr(agent, '_fetch', lambda user_id, tenant_id, conversation_id, name, args: {'found': results[args['query']]})
    (msgs, sources, _, _, _), _ = run(Model(calls(('one', 'search_documents', {'query': 'หนึ่ง'}), ('two', 'search_documents', {'query': 'สอง'})), answer()))
    assert [(s['chunk_id'], s['number']) for s in sources] == [('a', 1), ('b', 2), ('c', 3)]
    second = json.loads(tool_messages(msgs)['two'])
    assert [r['ref'] for r in second['results']] == [2, 3]  # the passage both searches found keeps one number


def test_a_model_without_tool_calling_falls_back_to_a_plain_answer():
    (msgs, sources, text, tin, tout), _ = run(Model(Reply({}, 400)))
    assert text is None and msgs == [{'role': 'user', 'content': 'q'}] and sources == []


def test_agent_chat_searches_documents_with_the_callers_permissions(department, monkeypatch):
    upload(department, 'ระเบียบการยืมอุปกรณ์สำนักงาน ต้องคืนภายในเจ็ดวัน', name='borrow.txt')
    member = department; member.post('/api/auth/logout'); assert login_as(member, 'member').status_code == 200  # a member asks about what the department added
    sent = []
    def respond(request):
        body = json.loads(request.content); sent.append(body)
        if len(sent) == 1:
            return httpx.Response(200, json={'usage': {'prompt_tokens': 10, 'completion_tokens': 2}, 'choices': [{'message': {'content': '', 'tool_calls': [{'id': 't1', 'function': {'name': 'search_documents', 'arguments': json.dumps({'query': 'ยืมอุปกรณ์สำนักงาน'})}}]}}]})
        return httpx.Response(200, json={'usage': {'prompt_tokens': 30, 'completion_tokens': 8}, 'choices': [{'message': {'content': 'ต้องคืนภายในเจ็ดวัน [1]'}}]})
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda *a, **kw: real(*a, **{**kw, 'transport': httpx.MockTransport(respond)}))
    r = member.post('/api/chat', json={'question': 'ยืมอุปกรณ์ต้องคืนเมื่อไร', 'agent': True})
    events = [json.loads(line) for line in r.text.splitlines()]
    assert 'ต้องคืนภายในเจ็ดวัน [1]' in ''.join(e.get('text', '') for e in events if e['type'] == 'delta')
    assert 'borrow.txt' in sent[1]['messages'][-1]['content']  # the tool result reached the model
    assert any(e['type'] == 'done' for e in events)
