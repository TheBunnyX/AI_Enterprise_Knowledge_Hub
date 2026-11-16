from conftest import login_as
import asyncio
from hub import agent

class R:
    def __init__(s,d,code=200):s.d=d;s.status_code=code
    def raise_for_status(s):pass
    def json(s):return s.d

class C:
    def __init__(s):s.n=0;s.payloads=[]
    async def post(s,url,headers=None,json=None):
        s.payloads.append(json);s.n+=1
        if s.n==1:return R({'usage':{'prompt_tokens':10,'completion_tokens':2},'choices':[{'message':{'content':'','tool_calls':[{'id':'a','function':{'name':'search_documents','arguments':'{"query":"x"}'}}]}}]})
        return R({'usage':{'prompt_tokens':20,'completion_tokens':5},'choices':[{'message':{'content':'ตอบ [1]'}}]})

def test_agent_loop_calls_tool_then_answers(monkeypatch):
    monkeypatch.setattr(agent,'_fetch',lambda uid,tid,cid,name,args:{'found':[{'chunk_id':'c1','name':'d','page':1,'snippet':'s','document_id':'d1'}]})
    status=[];c=C()
    msgs,sources,answer,tin,tout=asyncio.run(agent.agent_prepare(c,'http://x','k',{'api_id':'m'},[{'role':'user','content':'q'}],100,0,status.append,user_id='u',tenant_id='t',web=False))
    assert answer=='ตอบ [1]' and (tin,tout)==(30,7) and [s['number'] for s in sources]==[1]
    assert msgs[-1]['role']=='tool' and all(p.get('tools') for p in c.payloads)


def test_generated_files_build_and_download(member,client):
    import io,csv
    from hub import generated
    from hub.database import SessionLocal
    from hub.models import User
    from sqlalchemy import select
    with SessionLocal() as db:
        u=db.scalars(select(User).where(User.email=='member@local.test')).first() or db.scalars(select(User)).first()
        uid,tid=u.id,u.tenant_id
        deck=generated.create(db,uid,tid,'c1','pptx',{'title':'สรุป','slides':[{'title':'หัวข้อ','bullets':['ข้อ 1','ข้อ 2'],'notes':'n'}]})
        sheet=generated.create(db,uid,tid,'c1','csv',{'filename':'a/b:c','sheets':[{'columns':['ชื่อ','ค่า'],'rows':[['=HYPERLINK("x")',5],['-3','ok']]}]})
        xl=generated.create(db,uid,tid,'c1','xlsx',{'title':'t','sheets':[{'columns':['a'],'rows':[['=1+1']]}]})
        ids=(deck.id,sheet.id,xl.id);names=(deck.name,sheet.name,xl.name)
    assert names[1]=='a b c.csv'
    r=client.get('/api/files/'+ids[0]);assert r.status_code==200 and r.content[:2]==b'PK'
    from pptx import Presentation
    assert len(Presentation(io.BytesIO(r.content)).slides)==2
    r=client.get('/api/files/'+ids[1]);rows=list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))
    assert rows[1][0].startswith("'=") and rows[2][0]=='-3'
    from openpyxl import load_workbook
    ws=load_workbook(io.BytesIO(client.get('/api/files/'+ids[2]).content)).active
    assert ws['A2'].value=='=1+1' and ws['A2'].data_type=='s'
    assert client.get('/api/files').json()
    client.post('/api/auth/logout');login_as(client,'admin')
    assert client.get('/api/files/'+ids[0]).status_code==404  # other users cannot download it


def test_generated_file_limits():
    import pytest
    from hub import generated
    with pytest.raises(generated.ToolError):generated.build_pptx({'slides':[{'title':'x'}]*31})
    with pytest.raises(generated.ToolError):generated.build_xlsx({'sheets':[{'columns':['a'],'rows':[[1]]*2001}]})


def test_word_and_pdf_documents():
    import io,pytest
    from hub import generated
    args={'title':'รายงาน','sections':[{'heading':'ภาพรวม','paragraphs':['พนักงานทุกคนมีสิทธิ์ลาพักผ่อนประจำปี '*8],'bullets':['ข้อ 1'],'table':{'columns':['ก','ข'],'rows':[['=1',2]]}}]}
    pdf=generated.build_pdf(args);assert pdf.startswith(b'%PDF')
    from docx import Document
    doc=Document(io.BytesIO(generated.build_docx(args)))
    assert doc.paragraphs[0].text=='รายงาน' and doc.tables[0].rows[1].cells[0].text=='=1'
    with pytest.raises(generated.ToolError):generated.build_pdf({'sections':[]})
    lines=generated.wrap_lines('พนักงานทุกคนมีสิทธิ์ลาพักผ่อน '*5,100,lambda t:len(t)*6)
    assert len(lines)>1 and all(l and l[0] not in 'ะาำิีึืุู่้๊๋็' for l in lines)


def _catalog():
    return [{'id':'a/m1','name':'A: M1','context_length':8000,'input_price':0.5,'output_price':1.5,'inputs':['text'],'outputs':['text'],'tools':True},
            {'id':'a/free','name':'A: Free','context_length':8000,'input_price':0.0,'output_price':0.0,'inputs':['text'],'outputs':['text'],'tools':False},
            {'id':'openrouter/auto','name':'Auto','context_length':8000,'input_price':None,'output_price':None,'inputs':['text'],'outputs':['text'],'tools':True},
            {'id':'a/img','name':'Img','context_length':0,'input_price':1.0,'output_price':1.0,'inputs':['text'],'outputs':['image'],'tools':False}]

def test_openrouter_price_conversion_and_sync(admin,client,monkeypatch):
    from hub import openrouter_sync as o
    assert o.normalize({'id':'x','pricing':{'prompt':'0.0000005','completion':'0.0000015'}})['input_price']==0.5
    assert o.normalize({'id':'x','pricing':{'prompt':'-1','completion':'-1'}})['input_price'] is None
    async def fake(force=False):return _catalog()
    monkeypatch.setattr(o,'fetch_catalog',fake)
    r=client.get('/api/admin/openrouter/catalog?free=true');assert [i['id'] for i in r.json()['items']]==['a/free']
    assert client.post('/api/admin/openrouter/models',json={'api_id':'a/img'}).status_code==422
    r=client.post('/api/admin/openrouter/models',json={'api_id':'a/m1'});assert r.status_code==201
    assert client.post('/api/admin/openrouter/models',json={'api_id':'a/m1'}).status_code==409
    assert client.post('/api/admin/openrouter/models',json={'api_id':'openrouter/auto'}).json()['variable_price']
    p=client.get('/api/admin/openrouter/sync/preview').json();by={i['api_id']:i for i in p['items']}
    assert by['a/m1']['status']=='same' and by['openrouter/auto']['status']=='variable'
    mid=by['a/m1']['id']
    from hub.database import SessionLocal
    from hub.models import AIModel
    with SessionLocal() as db:m=db.get(AIModel,mid);m.input_price=9;db.commit()
    assert client.get('/api/admin/openrouter/sync/preview').json()['changed']==1
    r=client.post('/api/admin/openrouter/sync/apply',json={'ids':[]}).json();assert r['updated']==0
    r=client.post('/api/admin/openrouter/sync/apply',json={}).json();assert r['updated']==1
    with SessionLocal() as db:assert db.get(AIModel,mid).input_price==0.5

def test_openrouter_auto_sync_is_opt_in_and_throttled(admin,client,monkeypatch):
    from hub import openrouter_sync as o
    from hub.database import SessionLocal
    from hub.models import AIModel
    calls=[]
    async def fake(force=False):calls.append(1);return _catalog()
    monkeypatch.setattr(o,'fetch_catalog',fake)
    with SessionLocal() as db:
        m=AIModel(name='m1',provider='OpenRouter',api_id='a/m1',category='LLM',enabled=True,input_price=9,output_price=9);db.add(m);db.commit();mid=m.id
    o.run_auto_sync();assert not calls  # off by default
    assert client.put('/api/admin/openrouter/sync',json={'auto':True}).json()['auto'] is True
    o.run_auto_sync();assert len(calls)==1
    with SessionLocal() as db:assert db.get(AIModel,mid).input_price==0.5
    o.run_auto_sync();assert len(calls)==1  # within 5 minutes
    st=client.get('/api/admin/openrouter/sync').json();assert st['auto'] and st['last_status']=='ok' and st['last_changed']==1
    client.put('/api/admin/openrouter/sync',json={'auto':False});o.run_auto_sync();assert len(calls)==1

def test_openrouter_endpoints_require_admin(member,client):
    assert client.get('/api/admin/openrouter/sync').status_code in (401,403)
    assert client.put('/api/admin/openrouter/sync',json={'auto':True}).status_code in (401,403)


def test_openrouter_catalog_always_uses_official_url(monkeypatch):
    import asyncio,httpx
    from hub import openrouter_sync as o
    seen=[]
    class R:
        def raise_for_status(s):pass
        def json(s):return {'data':[{'id':'a/b','pricing':{'prompt':'0.000001','completion':'0.000002'}}]}
    class C:
        def __init__(s,*a,**k):pass
        async def __aenter__(s):return s
        async def __aexit__(s,*a):pass
        async def get(s,url):seen.append(url);return R()
    monkeypatch.setattr(httpx,'AsyncClient',C);o._cache.update(at=0,data=[])
    items=asyncio.run(o.fetch_catalog(force=True))
    assert seen==['https://openrouter.ai/api/v1/models'] and items[0]['input_price']==1.0 and items[0]['output_price']==2.0
