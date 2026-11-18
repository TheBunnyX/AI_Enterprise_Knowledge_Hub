"""The Agent's calculate, read_table, summarize_document, view_figure and save_to_library tools."""
import asyncio, io
import pytest
from sqlalchemy import select
from hub import agent, agent_tools
from hub.database import SessionLocal
from test_agent_graph import Model, calls, answer, tool_messages
from conftest import login_as
from test_platform import upload


# ---------- calculate ----------

def calc(*expressions): return agent_tools.calculate({'expressions': list(expressions)})['results']


def test_calculate_does_exact_arithmetic_and_the_listed_functions():
    out = calc('1250000*0.07', 'sum([12,30,8])/3', 'round(100*45/60,1)', 'max(3,9,4)', '2**10', '7//2 + 7%2', 'sqrt(16)', 'avg([1,2,3,4])', 'median([5,1,9])')
    assert [r['value'] for r in out] == [87500, 16.6666666667, 75, 9, 1024, 4, 4, 2.5, 5]


@pytest.mark.parametrize('bad', ['__import__("os").system("id")', 'open("/etc/passwd")', 'x+1', '"a"*5', '(1).__class__', '[i for i in range(3)]', 'lambda: 1', '9**9**9', '10**1000', 'sum(range(10))', '1 if True else 2', 'True+1'])
def test_calculate_runs_nothing_but_arithmetic(bad):
    out = calc(bad)[0]
    assert 'error' in out and 'value' not in out


def test_calculate_reports_division_by_zero_and_keeps_the_other_expressions():
    a, b = calc('1/0', '2+2')
    assert 'error' in a and b['value'] == 4


def test_calculate_needs_expressions_and_caps_their_number():
    assert 'error' in agent_tools.calculate({})
    assert len(calc(*['1+1'] * 15)) == agent_tools.MAX_EXPRESSIONS
    assert agent_tools.calculate({'expression': '3*3'})['results'][0]['value'] == 9  # a model that sends one string anyway


def test_the_agent_calculates_through_the_tool_instead_of_guessing():
    model = Model(calls(('c1', 'calculate', {'expressions': ['1250000*0.07']})), answer('ภาษี 87,500 บาท'))
    status = []
    msgs, sources, text, _, _ = asyncio.run(agent.agent_prepare(model, 'http://x', 'k', {'api_id': 'm'}, [{'role': 'user', 'content': 'q'}], 100, 0, status.append, user_id='u', tenant_id='t', web=False))
    assert '87500' in tool_messages(msgs)['c1'] and text.startswith('ภาษี')
    assert 'calculate' in {t['function']['name'] for t in model.payloads[0]['tools']}


# ---------- helpers for the tools that read documents ----------

def who(client): return client.get('/api/auth/me').json()


def fetch(client, name, args):
    me = who(client)
    return agent._fetch(me['id'], me['tenant_id'], '', name, args)


def run_agent(client, model, pause=None, **kw):
    me = who(client)
    return asyncio.run(agent.agent_prepare(model, 'http://x', 'k', {'api_id': 'm'}, [{'role': 'user', 'content': 'q'}], 100, 0, lambda s: None, user_id=me['id'], tenant_id=me['tenant_id'], web=False, conversation_id='conv', pause=pause, **kw))


def xlsx_bytes():
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = 'งบ'
    ws.append(['รายการ', 'ไตรมาส 1', 'ไตรมาส 2'])
    for i in range(1, 151): ws.append([f'หมวด {i}', i * 10, i * 12.5])
    ws2 = wb.create_sheet('สรุป'); ws2.append(['รวม', 1])
    out = io.BytesIO(); wb.save(out); return out.getvalue()


def put(client, name, data, kb=None):
    kb = kb or client.get('/api/knowledge-bases').json()[0]['id']
    r = client.post('/api/documents', data={'knowledge_base_id': kb}, files={'file': (name, data, 'application/octet-stream')})
    assert r.status_code == 201, r.text
    return r.json()['id']


# ---------- read_table ----------

def test_read_table_returns_columns_rows_and_pages_through_a_sheet(department):
    did = put(department, 'budget.xlsx', xlsx_bytes())
    first = fetch(department, 'read_table', {'document_id': did})['table']
    assert first['columns'] == ['รายการ', 'ไตรมาส 1', 'ไตรมาส 2'] and first['sheet'] == 'งบ' and first['sheets'] == ['งบ', 'สรุป']
    assert len(first['rows']) == 100 and first['rows'][0] == ['หมวด 1', 10, 12.5] and first['total_rows'] == 150 and (first['from'], first['to']) == (1, 100)
    rest = fetch(department, 'read_table', {'document_id': did, 'row_from': 101})['table']
    assert [r[0] for r in rest['rows']][:2] == ['หมวด 101', 'หมวด 102'] and rest['to'] == 150
    other = fetch(department, 'read_table', {'document_id': did, 'sheet': 'สรุป'})['table']
    assert other['columns'] == ['รวม', 1] and other['rows'] == []


def test_read_table_reads_csv_and_refuses_other_files_and_unknown_documents(department):
    csv_id = put(department, 'sales.csv', 'เดือน,ยอด\nม.ค.,100\nก.พ.,250\n'.encode('utf-8-sig'))
    t = fetch(department, 'read_table', {'document_id': csv_id})['table']
    assert t['columns'] == ['เดือน', 'ยอด'] and t['rows'] == [['ม.ค.', '100'], ['ก.พ.', '250']]
    txt = put(department, 'note.txt', 'ข้อความธรรมดา สำหรับทดสอบเครื่องมืออ่านตาราง'.encode())
    assert 'error' in fetch(department, 'read_table', {'document_id': txt})['result']
    assert 'error' in fetch(department, 'read_table', {'document_id': 'no-such-document'})['result']


def test_a_table_result_gets_a_citation_number_and_never_overflows_the_context(department):
    did = put(department, 'budget.xlsx', xlsx_bytes())
    raw = fetch(department, 'read_table', {'document_id': did})
    result, cards = agent._present(raw, 0, {})
    assert result['ref'] == 1 and cards[0]['name'] == 'budget.xlsx'
    assert len(agent._clip(result)) <= agent.RESULT_CHARS + 20 and 'row_from=' in result.get('note', '')  # told how to read on


def test_read_table_only_serves_documents_the_user_may_read(client):
    login_as(client, 'department')
    did = put(client, 'budget.xlsx', xlsx_bytes())
    assert 'table' in fetch(client, 'read_table', {'document_id': did})
    other = who(client)['tenant_id']
    from hub.models import Organization
    with SessionLocal() as db:
        foreign = Organization(name='Tenant B'); db.add(foreign); db.commit(); db.refresh(foreign)
    from hub.models import User
    with SessionLocal() as db:
        stranger = User(tenant_id=foreign.id, email='x@b.test', name='X', role='USER', password_hash='x'); db.add(stranger); db.commit(); sid = stranger.id
    assert 'error' in agent._fetch(sid, foreign.id, '', 'read_table', {'document_id': did})['result']  # another organisation's document id leaks nothing


# ---------- summarize_document ----------

LONG = '\n\n'.join(f'ข้อ {i}. ' + 'พนักงานมีสิทธิ์ลาพักร้อนตามอายุงาน และต้องแจ้งล่วงหน้า ' * 6 for i in range(1, 60))


def test_summarize_document_summarises_each_section_and_counts_every_model_call(department):
    did = put(department, 'policy.txt', LONG.encode())
    model = Model(calls(('s1', 'summarize_document', {'document_id': did})), answer('สรุปส่วน'), answer('สรุปส่วน'), answer('สรุปส่วน'), answer('สรุปทั้งฉบับ'))
    msgs, sources, text, tin, tout = run_agent(department, model)
    out = tool_messages(msgs)['s1']
    assert '"sections"' in out and 'สรุปส่วน' in out and text == 'สรุปทั้งฉบับ'
    summaries = [p for p in model.payloads if p['messages'][0]['role'] == 'system' and 'สรุปเนื้อหาส่วนนี้' in p['messages'][0]['content']]
    assert len(summaries) >= 2  # a long document is split
    assert 'tools' not in summaries[0]  # the section prompts are plain completions
    assert tin == 10 + 20 * len(summaries) + 20  # the planning call, each section, the final answer: all metered
    assert sources and sources[0]['name'] == 'policy.txt'


def test_summarize_document_says_when_it_stopped_short_and_where_to_continue(department, monkeypatch):
    monkeypatch.setattr(agent_tools, 'MAX_SECTIONS', 1)
    did = put(department, 'policy.txt', LONG.encode())
    msgs, _, _, _, _ = run_agent(department, Model(calls(('s1', 'summarize_document', {'document_id': did})), answer('x')))
    assert 'page_from=' in tool_messages(msgs)['s1']


def test_summarize_document_refuses_unknown_documents_and_survives_failing_summaries(department):
    msgs, _, _, _, _ = run_agent(department, Model(calls(('s1', 'summarize_document', {'document_id': 'nope'})), answer('ok')))
    assert 'ไม่พบเอกสาร' in tool_messages(msgs)['s1']
    did = put(department, 'policy.txt', LONG.encode())

    class Down(Model):
        async def post(self, url, headers=None, json=None):
            self.payloads.append(json)
            if json['messages'][0]['role'] == 'system': raise RuntimeError('provider down')
            return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
    msgs, _, text, _, _ = run_agent(department, Down(calls(('s1', 'summarize_document', {'document_id': did})), answer('ตอบจากที่มี')))
    assert text == 'ตอบจากที่มี' and 'ขัดข้อง' in tool_messages(msgs)['s1']  # every section failed: reported to the model, the answer still comes


# ---------- view_figure ----------

def picture_chunk(client, with_key=True):
    from hub import storage
    from hub.models import Chunk
    did = put(client, 'figure.txt', 'แผนภูมิแสดงยอดขายรายไตรมาส'.encode())
    me = who(client)
    with SessionLocal() as db:
        base = db.scalar(select(Chunk).where(Chunk.document_id == did))
        key = f"{me['tenant_id']}/test-figure.jpg"
        storage.put(key, b'\xff\xd8\xff\xe0fake-jpeg')
        c = Chunk(tenant_id=base.tenant_id, document_id=did, page=3, text='กราฟแท่งยอดขาย ไตรมาส 3 สูงสุด', kind='image', image_key=key if with_key else '', embedding_version=base.embedding_version)
        db.add(c); db.commit(); return did, c.id


def test_view_figure_finds_the_picture_by_chunk_or_by_page_and_the_agent_attaches_it(department, monkeypatch):
    did, chunk = picture_chunk(department)
    by_chunk = fetch(department, 'view_figure', {'chunk_id': chunk})['figure']
    by_page = fetch(department, 'view_figure', {'document_id': did, 'page': 3})['figure']
    assert by_chunk['chunk_id'] == by_page['chunk_id'] == chunk and by_chunk['page'] == 3 and 'ยอดขาย' in by_chunk['caption']
    assert 'error' in fetch(department, 'view_figure', {'document_id': did, 'page': 9})['result']
    assert 'error' in fetch(department, 'view_figure', {})['result']
    monkeypatch.setattr(agent.multimodal, 'enabled', lambda: True)
    monkeypatch.setattr(agent.multimodal, 'supports_vision', lambda used: True)
    model = Model(calls(('v1', 'view_figure', {'chunk_id': chunk})), answer('ไตรมาส 3 สูงสุด [1]'))
    msgs, sources, text, _, _ = run_agent(department, model)
    assert 'ภาพแนบมาในข้อความถัดไป' in tool_messages(msgs)['v1']
    last = msgs[-1]
    assert last['role'] == 'user' and any(p.get('type') == 'image_url' and p['image_url']['url'].startswith('data:image/jpeg;base64,') for p in last['content'])  # after every tool answer
    assert msgs.index(last) > max(i for i, m in enumerate(msgs) if m['role'] == 'tool')
    assert sources[0]['kind'] == 'image' and 'view_figure' in {t['function']['name'] for t in model.payloads[0]['tools']}


def test_view_figure_is_offered_only_to_a_model_that_can_see(department, monkeypatch):
    monkeypatch.setattr(agent.multimodal, 'enabled', lambda: True)
    monkeypatch.setattr(agent.multimodal, 'supports_vision', lambda used: False)
    model = Model(answer('ตอบ'))
    run_agent(department, model)
    assert 'view_figure' not in {t['function']['name'] for t in model.payloads[0]['tools']}


def test_a_question_may_bring_in_only_a_few_pictures(department, monkeypatch):
    _, chunk = picture_chunk(department)
    monkeypatch.setattr(agent.multimodal, 'enabled', lambda: True)
    monkeypatch.setattr(agent.multimodal, 'supports_vision', lambda used: True)
    many = [(f'v{i}', 'view_figure', {'chunk_id': chunk, 'page': i}) for i in range(agent_tools.MAX_FIGURES + 1)]  # one round runs at most MAX_PARALLEL calls
    msgs, _, _, _, _ = run_agent(department, Model(calls(*many), answer('x')))
    pictures = [m for m in msgs if m['role'] == 'user' and isinstance(m['content'], list)]
    assert sum(1 for m in pictures for p in m['content'] if p.get('type') == 'image_url') == agent_tools.MAX_FIGURES
    assert sum('ไม่เกิน' in m['content'] for m in msgs if m['role'] == 'tool') == 1  # the extra picture is refused, not silently dropped


def test_search_hits_that_are_pictures_say_so_and_carry_their_chunk_id():
    raw = {'found': [{'chunk_id': 'c9', 'document_id': 'd', 'name': 'a.pdf', 'page': 2, 'snippet': 'คำอธิบายภาพ', 'kind': 'image'}]}
    result, _ = agent._present(raw, 0, {})
    assert result['results'][0]['kind'] == 'picture' and result['results'][0]['chunk_id'] == 'c9'


# ---------- save_to_library ----------

def make_file(client):
    from hub import generated
    me = who(client)
    with SessionLocal() as db:
        f = generated.create(db, me['id'], me['tenant_id'], '', 'docx', {'title': 'รายงานสรุปนโยบายลา', 'sections': [{'heading': 'ภาพรวม', 'paragraphs': ['พนักงานลาพักร้อนได้ตามอายุงาน']}]})
        return f.id


def names_of(model): return {t['function']['name'] for t in model.payloads[0]['tools']}


def test_the_agent_asks_before_saving_and_stores_the_file_only_after_approval(department):
    fid = make_file(department); kb = department.get('/api/knowledge-bases').json()[0]
    before = len(department.get('/api/documents').json())
    pause = []
    model = Model(calls(('s1', 'save_to_library', {'file_id': fid, 'knowledge_base_id': kb['id']})), answer('บันทึกแล้ว'))
    msgs, _, text, _, _ = run_agent(department, model, pause=pause)
    assert pause[0]['kind'] == 'approval' and pause[0]['tool'] == 'save_to_library' and pause[0]['knowledge_base'] == kb['name'] and pause[0]['file'].endswith('.docx')
    assert kb['name'] in text and 'อนุญาต' in text
    assert len(department.get('/api/documents').json()) == before  # nothing is stored while the person has not answered
    again = []
    me = who(department)
    msgs, _, text, _, _ = asyncio.run(agent.agent_prepare(model, 'http://x', 'k', {'api_id': 'm'}, [{'role': 'user', 'content': 'ok'}], 100, 0, lambda s: None, user_id=me['id'], tenant_id=me['tenant_id'], web=False, conversation_id='conv', pause=again, thread_id=pause[0]['thread_id'], resume={'approve': True}))
    assert text == 'บันทึกแล้ว' and '"ok": true' in tool_messages(msgs)['s1']
    docs = department.get('/api/documents').json()
    assert len(docs) == before + 1 and any(d['name'].endswith('.docx') and d['knowledge_base_id'] == kb['id'] for d in docs)


def test_a_refused_save_stores_nothing_and_tells_the_model(department):
    fid = make_file(department); kb = department.get('/api/knowledge-bases').json()[0]
    before = len(department.get('/api/documents').json())
    pause = []
    model = Model(calls(('s1', 'save_to_library', {'file_id': fid, 'knowledge_base_id': kb['id']})), answer('ไม่ได้บันทึก'))
    run_agent(department, model, pause=pause)
    me = who(department)
    msgs, _, text, _, _ = asyncio.run(agent.agent_prepare(model, 'http://x', 'k', {'api_id': 'm'}, [{'role': 'user', 'content': 'no'}], 100, 0, lambda s: None, user_id=me['id'], tenant_id=me['tenant_id'], web=False, conversation_id='conv', pause=[], thread_id=pause[0]['thread_id'], resume={'approve': False}))
    assert 'ไม่อนุญาต' in tool_messages(msgs)['s1'] and len(department.get('/api/documents').json()) == before


def test_saving_is_refused_up_front_for_another_users_file_or_a_library_the_user_cannot_write(client):
    login_as(client, 'department'); fid = make_file(client); kb = client.get('/api/knowledge-bases').json()[0]
    login_as(client, 'member'); member = client
    me = who(member)
    with SessionLocal() as db:
        from hub.models import User
        u = db.get(User, me['id'])
        assert 'ไม่พบไฟล์' in agent_tools.check_save(db, u, {'file_id': fid, 'knowledge_base_id': kb['id']})  # a file of someone else
    own = make_file(member)
    with SessionLocal() as db:
        from hub.models import User
        u = db.get(User, me['id'])
        assert 'ไม่มีสิทธิ์' in agent_tools.check_save(db, u, {'file_id': own, 'knowledge_base_id': kb['id']})  # members cannot add documents


def test_the_save_tool_is_offered_only_to_people_who_can_add_documents_and_can_answer_a_question(client):
    login_as(client, 'department')
    d = Model(answer('x')); run_agent(client, d, pause=[]); assert 'save_to_library' in names_of(d)
    one_shot = Model(answer('x')); run_agent(client, one_shot); assert 'save_to_library' not in names_of(one_shot)  # nobody could confirm
    login_as(client, 'member')
    m = Model(answer('x')); run_agent(client, m, pause=[]); assert 'save_to_library' not in names_of(m)


def test_an_approval_to_save_is_not_blocked_by_the_web_search_policy(department):
    """Switching web search off must deny web approvals only: chat_service reads the saved tool name."""
    import inspect
    from hub import chat_service
    source = inspect.getsource(chat_service)
    assert "run.pending.get('tool')!='web_search' or web_policy!='off'" in source


def test_saving_uses_the_same_checks_as_an_upload(department, monkeypatch):
    fid = make_file(department); kb = department.get('/api/knowledge-bases').json()[0]
    from hub import uploads
    from fastapi import HTTPException
    def infected(name, data): raise HTTPException(422, 'พบไวรัสในไฟล์')
    monkeypatch.setattr(uploads, 'check_bytes', infected)
    me = who(department)
    with SessionLocal() as db:
        from hub.models import User
        out = agent_tools.save(db, db.get(User, me['id']), {'file_id': fid, 'knowledge_base_id': kb['id']})
    assert out['result']['error'] == 'พบไวรัสในไฟล์'
    assert not any(d['name'].endswith('.docx') for d in department.get('/api/documents').json())


# ---------- the prompt ----------

def test_the_prompt_tells_the_agent_how_to_find_conflicts_between_documents():
    p = agent.AGENT_PROMPT
    assert 'ขัดแย้ง' in p and 'calculate' in p and 'summarize_document' in p and 'read_table' in p
