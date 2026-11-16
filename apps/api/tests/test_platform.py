import io, json, math
from sqlalchemy import select
from hub.database import SessionLocal
from hub.models import Document, Chunk, Conversation, Message, Usage, Audit
from hub.retrieval import embed, parse

def upload(c,text='นโยบายลาพักร้อน พนักงานลาได้สิบวันต่อปี',kb=None,name='test.txt'):
    kb=kb or c.get('/api/knowledge-bases').json()[0]['id']
    return c.post('/api/documents',data={'knowledge_base_id':kb},files={'file':(name,text.encode(),'text/plain')})

def test_authentication_required(client):
    for route in ('/api/documents','/api/knowledge-bases','/api/analytics','/api/audit','/api/admin/users','/api/conversations'):
        assert client.get(route).status_code==401

def test_session_logout_and_cookie(member):
    assert member.get('/api/auth/me').json()['role']=='USER'
    member.post('/api/auth/logout');assert member.get('/api/auth/me').status_code==401

def test_member_cannot_admin(member):
    for route in ('/api/admin/organizations','/api/admin/users','/api/system'):
        assert member.get(route).status_code==403
    assert member.post('/api/knowledge-bases',json={'name':'unauthorized'}).status_code==403

def test_upload_dedup_parse_and_download(department):
    r=upload(department);assert r.status_code==201
    id=r.json()['id'];doc=department.get('/api/documents/'+id).json()
    assert doc['status']=='ready' and doc['pages'][0]['page']==1
    assert 'สิบวัน' in doc['pages'][0]['text']
    assert upload(department).json()['duplicate'] is True
    assert department.get('/api/documents/'+id+'/download').content.decode().startswith('นโยบาย')

def test_upload_validation(department):
    assert upload(department,'bad',name='evil.exe').status_code==415
    assert upload(department,'not pdf',name='fake.pdf').status_code==415
    assert upload(department,'',name='empty.txt').status_code==413
    assert upload(department,'zip',name='fake.docx').status_code==415

def test_tenant_isolation_documents_search_and_download(department,other_tenant):
    id=upload(department,'ALPHA-SECRET private knowledge').json()['id']
    assert department.post('/api/auth/login',json={'email':'b@example.test','password':'testing-password-B'}).status_code==200
    assert department.get('/api/documents').json()==[]
    assert department.get('/api/documents/'+id).status_code==404
    assert department.get('/api/documents/'+id+'/download').status_code==404
    assert department.get('/api/search',params={'q':'ALPHA-SECRET'}).json()==[]
    assert upload(department,'data',kb='not-found').status_code==404

def test_tenant_isolation_conversations(member,other_tenant):
    r=member.post('/api/chat',json={'question':'ลาพักร้อนได้กี่วัน'})
    meta=json.loads(r.text.splitlines()[0]);id=meta['conversation_id']
    member.post('/api/auth/login',json={'email':'b@example.test','password':'testing-password-B'})
    assert member.get('/api/conversations/'+id).status_code==404
    assert member.post('/api/chat',json={'question':'secret','conversation_id':id}).status_code==404

def test_grounded_chat_citations_and_usage(member):
    r=member.post('/api/chat',json={'question':'ลาพักร้อนได้กี่วัน'})
    assert r.status_code==200
    events=[json.loads(l) for l in r.text.splitlines()]
    assert events[0]['type']=='meta' and events[-1]['type']=='done'
    assert events[0]['citations']
    c=events[0]['citations'][0]
    assert member.get('/api/documents/'+c['document_id']).status_code==200
    answer=''.join(e.get('text','') for e in events)
    assert 'คำตอบทดสอบ' in answer and '10 วัน' in answer
    assert len(member.get('/api/conversations/'+events[0]['conversation_id']).json())==2
    assert member.get('/api/analytics').json()['requests']==1
    assert 'ถามคำถาม' in str(member.get('/api/audit').json())

def test_no_evidence_does_not_invent_sources(member):
    r=member.post('/api/chat',json={'question':'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz'})
    meta=json.loads(r.text.splitlines()[0]);assert meta['citations']==[]
    assert 'ยังไม่พบหลักฐาน' in ''.join(json.loads(l).get('text','') for l in r.text.splitlines())

def test_org_management_and_quota(admin):
    org=admin.post('/api/admin/organizations',json={'name':'Test tenant','quota':0}).json()
    assert org['id'] in [o['id'] for o in admin.get('/api/admin/organizations').json()]
    from hub.database import SessionLocal
    from hub.ops_models import Group
    with SessionLocal() as db:
        g=Group(tenant_id=org['id'],name='ฝ่ายทดสอบ',kind='department');db.add(g);db.commit();gid=g.id
    body={'name':'Quota user','email':'quota@example.test','tenant_id':org['id'],'password':'long-enough-password','role':'USER'}
    assert admin.post('/api/admin/users',json=body).status_code==422
    r=admin.post('/api/admin/users',json={**body,'department_id':gid})
    assert r.status_code==201
    admin.post('/api/auth/login',json={'email':'quota@example.test','password':'long-enough-password'})
    assert admin.post('/api/chat',json={'question':'hello'}).status_code==429

def login_as(client,email):
    from hub.database import DATA
    password=(DATA/'dev-password.txt').read_text()
    assert client.post('/api/auth/login',json={'email':email,'password':password}).status_code==200

def test_department_admin_scope(admin):
    users={u['email']:u['id'] for u in admin.get('/api/admin/users').json()}
    own=admin.get('/api/groups').json()[0]
    other=admin.post('/api/team/departments',json={'name':'ฝ่ายอื่น'}).json()['id']
    admin.post(f'/api/team/departments/{other}/members',json={'user_id':users['admin@local.test']})
    login_as(admin,'department@local.test')
    assert admin.get('/api/auth/me').json()['role']=='DEPARTMENT_ADMIN'
    assert admin.get('/api/tenant/users').status_code==200
    assert admin.get('/api/admin/users').status_code==403
    assert admin.get('/api/admin/gateway').status_code==403
    # departments are managed only through /api/team; /groups handles plain groups
    assert admin.put('/api/groups/'+own['id'],json={'name':own['name'],'kind':'department','members':list(users.values())}).status_code==422
    assert admin.put('/api/groups/'+own['id'],json={'name':own['name'],'kind':'group','members':[]}).status_code==422
    assert admin.post('/api/groups',json={'name':'ฝ่ายแอบสร้าง','kind':'department','members':[]}).status_code==422
    assert admin.put('/api/groups/'+other,json={'name':'ฝ่ายอื่น','kind':'department','members':[]}).status_code==422
    created=admin.post('/api/groups',json={'name':'ทีมใหม่','kind':'group','members':[]}).json()['id']
    assert users['department@local.test'] in next(g for g in admin.get('/api/groups').json() if g['id']==created)['members']

def test_user_cannot_manage(admin):
    login_as(admin,'member@local.test')
    assert admin.get('/api/auth/me').json()['role']=='USER'
    assert admin.get('/api/tenant/users').status_code==403
    assert admin.post('/api/groups',json={'name':'x','kind':'group','members':[]}).status_code==403
    assert admin.get('/api/admin/users').status_code==403

def test_models_and_no_secret_leak(admin,monkeypatch):
    monkeypatch.delenv('LITELLM_URL',raising=False)
    r=admin.post('/api/admin/models',json={'name':'Custom','provider':'LiteLLM','api_id':'configured-model','enabled':True})
    assert r.status_code==201
    models=admin.get('/api/models').json()
    m=next(m for m in models if m['id']==r.json()['id']);assert not m['configured']
    assert 'secret' not in str(models).lower()
    assert admin.post('/api/chat',json={'question':'นโยบาย','model_id':m['id']}).status_code==503

def test_unconfigured_media_honest(member):
    for kind in ('image','video','stt','tts'): assert member.post('/api/studio/'+kind,json={'prompt':'test'}).status_code==503

def test_csrf_protection(member):
    assert member.post('/api/auth/logout',headers={'origin':'https://untrusted.example'}).status_code==403
    assert member.get('/api/auth/me').status_code==200

def test_hybrid_search_and_filters(member):
    kb=member.get('/api/knowledge-bases').json()[0]['id']
    for mode in ('keyword','semantic','hybrid'):
        results=member.get('/api/search',params={'q':'ลาพักร้อน','mode':mode,'kb_id':kb})
        assert results.status_code==200
        assert all(r['knowledge_base_id']==kb for r in results.json())

def test_search_falls_back_to_approximate_matches(member):
    r=member.get('/api/search',params={'q':'qzxwvk-no-such-term'})
    assert r.status_code==200
    assert len(r.json())<=5 and all(x.get('approx') for x in r.json())  # only the loose fallback may answer, and it says so

def test_delete_removes_retrieval(admin):
    id=upload(admin,'unique-record-to-delete 123456').json()['id']
    assert admin.delete('/api/documents/'+id).status_code==200
    assert admin.get('/api/documents/'+id).status_code==404
    with SessionLocal() as db: assert db.scalar(select(Chunk).where(Chunk.document_id==id)) is None

def test_embedding_and_office_parsers():
    assert math.isclose(sum(v*v for v in embed('ความรู้')),1,rel_tol=1e-6)
    from docx import Document as Word
    from pptx import Presentation
    from openpyxl import Workbook
    f=io.BytesIO();w=Word();w.add_paragraph('Thai knowledge');w.save(f);assert 'Thai knowledge' in parse('x.docx',f.getvalue())[0][1]
    f=io.BytesIO();p=Presentation();s=p.slides.add_slide(p.slide_layouts[1]);s.shapes.title.text='Slide source';p.save(f);assert 'Slide source' in parse('x.pptx',f.getvalue())[0][1]
    f=io.BytesIO();w=Workbook();w.active.append(['Budget',100]);w.save(f);assert 'Budget' in parse('x.xlsx',f.getvalue())[0][1]

def test_csv_export(member):
    r=member.get('/api/usage/export');assert r.status_code==200
    assert 'text/csv' in r.headers['content-type'] and 'tenant_id' in r.text

def test_gateway_usage_and_cost_estimate(admin,monkeypatch):
    import httpx
    monkeypatch.setenv('LITELLM_URL','http://gateway.test/v1')
    monkeypatch.setenv('LITELLM_KEY','test-only-key')
    original=httpx.AsyncClient
    def respond(request):
        payload=json.loads(request.content)
        assert request.url.path=='/v1/chat/completions'
        assert payload['model']=='test-gateway-alias'
        assert '10 วัน' in payload['messages'][1]['content']
        return httpx.Response(200,json={'choices':[{'message':{'content':'พบข้อมูลการลาพักร้อนจากเอกสาร'}}],'usage':{'prompt_tokens':250,'completion_tokens':500}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond)))
    model=admin.post('/api/admin/models',json={'name':'Test gateway','provider':'LiteLLM','api_id':'test-gateway-alias','enabled':True,'input_price':2,'output_price':6}).json()['id']
    r=admin.post('/api/chat',json={'question':'ลาพักร้อน','model_id':model})
    assert r.status_code==200
    a=admin.get('/api/analytics').json()
    assert a['input_tokens']==250 and a['output_tokens']==500
    assert math.isclose(a['cost'],.0035) and a['estimated'] is True
