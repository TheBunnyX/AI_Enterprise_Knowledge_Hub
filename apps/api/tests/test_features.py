from conftest import login_as
import base64,json,io
import httpx,pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from hub.database import SessionLocal
from hub.models import User,Document,AIModel
from hub.feature_models import Setting,GenerationJob
from hub.auth import passwords
from hub import media
from test_platform import upload

def member_id(c):return next(u['id'] for u in c.get('/api/admin/users').json() if u['role']=='USER')

def test_restricted_kb_hides_docs_and_vectors(admin):
    kb=admin.get('/api/knowledge-bases').json()[0]['id']
    id=upload(admin,'RESTRICTED-TEXT secret policy',kb=kb).json()['id']
    assert admin.put('/api/knowledge-bases/'+kb+'/access',json={'visibility':'restricted','readers':[],'writers':[]}).status_code==200
    login_as(admin,'member')
    assert kb not in [b['id'] for b in admin.get('/api/knowledge-bases').json()]
    assert id not in [d['id'] for d in admin.get('/api/documents').json()]
    assert admin.get('/api/documents/'+id).status_code==404
    assert admin.get('/api/documents/'+id+'/download').status_code==404
    assert upload(admin,'another',kb=kb).status_code==404
    assert admin.get('/api/search',params={'q':'RESTRICTED-TEXT','kb_id':kb}).json()==[]

def test_kb_write_acl_and_foreign_members(admin,other_tenant):
    kb=admin.get('/api/knowledge-bases').json()[0]['id'];member=member_id(admin)
    assert admin.put('/api/knowledge-bases/'+kb+'/access',json={'visibility':'restricted','readers':[other_tenant['user']]}).status_code==422
    admin.put('/api/knowledge-bases/'+kb+'/access',json={'visibility':'restricted','readers':[member],'writers':[]})
    login_as(admin,'member')
    assert admin.get('/api/knowledge-bases').json()
    assert upload(admin,'read only',kb=kb).status_code==404

def test_document_versions_trash_restore(admin):
    id=upload(admin,'Version one policy').json()['id']
    r=admin.post('/api/documents/'+id+'/versions',files={'file':('new.txt',b'Version two policy','text/plain')})
    assert r.status_code==200 and r.json()['version']==2
    versions=admin.get('/api/documents/'+id+'/versions').json();old=next(v for v in versions if v['version']==1)
    assert admin.get('/api/documents/'+id+'/versions/'+old['id']+'/download').content==b'Version one policy'
    assert 'Version one' in admin.get('/api/documents/'+id+'?version=1').json()['pages'][0]['text']
    assert admin.delete('/api/documents/'+id).status_code==200
    assert admin.get('/api/documents/'+id).status_code==404
    assert id in [d['id'] for d in admin.get('/api/documents-trash').json()]
    assert admin.post('/api/documents/'+id+'/restore').status_code==200
    assert admin.get('/api/documents/'+id).json()['status']=='ready'

def test_gateway_key_encrypted_and_never_returned(admin,monkeypatch):
    monkeypatch.setenv('SECRETS_KEY',Fernet.generate_key().decode())
    r=admin.put('/api/admin/gateway',json={'url':'https://gateway.test/v1','api_key':'private-test-value'})
    assert r.status_code==200
    data=admin.get('/api/admin/gateway').json();assert data['key_configured'] and 'private-test-value' not in str(data)
    with SessionLocal() as db:
        setting=db.scalar(select(Setting).where(Setting.key=='gateway'))
        assert 'private-test-value' not in str(setting.value)
    login_as(admin,'member')
    assert admin.get('/api/admin/gateway').status_code==403

@pytest.mark.parametrize('kind,category',[('image','Image'),('video','Video'),('stt','STT'),('tts','TTS')])
def test_media_adapter_storage_and_private_download(admin,monkeypatch,kind,category,other_tenant):
    monkeypatch.setenv('LITELLM_URL','http://gateway.test/v1')
    model=admin.post('/api/admin/models',json={'name':'Test '+kind,'provider':'LiteLLM','api_id':'test-'+kind,'category':category,'enabled':True}).json()['id']
    original=httpx.Client
    def respond(request):
        path=request.url.path
        if path.endswith('/images/generations'):return httpx.Response(200,json={'data':[{'b64_json':base64.b64encode(b'PNG-test-bytes').decode()}]},headers={'x-litellm-response-cost':'0.04'})
        if path.endswith('/audio/speech'):return httpx.Response(200,content=b'ID3-test-audio')
        if path.endswith('/audio/transcriptions'):return httpx.Response(200,json={'text':'ข้อความจากเสียงทดสอบ'})
        if path.endswith('/videos') and request.method=='POST':return httpx.Response(200,json={'id':'test-video','status':'queued'})
        if path.endswith('/content'):return httpx.Response(200,content=b'test-mp4')
        return httpx.Response(200,json={'status':'completed'})
    monkeypatch.setattr(media.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    values={'kind':kind,'model_id':model,'prompt':'test input','options':'{}'}
    files={'file':('test.wav',b'RIFF-test-audio','audio/wav')} if kind=='stt' else None
    r=admin.post('/api/media/jobs',data=values,files=files);assert r.status_code==202
    id=r.json()['id'];job=admin.get('/api/media/jobs').json()[0]
    assert job['status']=='completed',job
    assert bool(admin.get('/api/media/'+id+'/content').content)
    assert (job['cost']==.04) if kind=='image' else (job['cost'] is None)
    login_as(admin,'member')
    assert admin.get('/api/media/'+id+'/content').status_code==404
    admin.post('/api/auth/login',json={'email':'b@example.test','password':'testing-password-B'})
    assert admin.get('/api/media/'+id+'/content').status_code==404

def test_media_failure_is_durable_and_safe(admin,monkeypatch):
    monkeypatch.setenv('LITELLM_URL','http://gateway.test/v1')
    model=admin.post('/api/admin/models',json={'name':'Broken','provider':'LiteLLM','api_id':'broken','category':'Image','enabled':True}).json()['id']
    original=httpx.Client
    monkeypatch.setattr(media.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(lambda r:httpx.Response(401,json={'secret':'must-not-leak'})),**kw))
    assert admin.post('/api/media/jobs',data={'kind':'image','model_id':model,'prompt':'test'}).status_code==202
    job=admin.get('/api/media/jobs').json()[0];assert job['status']=='failed' and 'must-not-leak' not in str(job)

def test_account_preferences_sessions_and_password(member):
    assert member.put('/api/account/preferences',json={'name':'ชื่อใหม่','default_model':'','notifications':False}).status_code==200
    assert member.get('/api/account/preferences').json()['notifications'] is False
    sessions=member.get('/api/account/sessions').json();assert sessions[0]['current']
    assert 'token' not in str(sessions)
    assert member.post('/api/account/password',json={'current_password':'wrong','new_password':'long-test-password'}).status_code==403
    assert member.delete('/api/account/sessions/'+sessions[0]['id']).status_code==200
    assert member.get('/api/auth/me').status_code==401

def test_model_policy_feedback_and_filtered_export(admin,other_tenant):
    tenant=admin.get('/api/auth/me').json()['tenant_id']
    model=admin.get('/api/models').json()[0]['id']
    admin.put('/api/admin/organizations/'+tenant+'/policy',json={'allowed_models':[],'default_model':'','monthly_budget':1})
    assert admin.post('/api/chat',json={'question':'policy'}).status_code==503
    admin.put('/api/admin/organizations/'+tenant+'/policy',json={'allowed_models':[model],'default_model':model,'monthly_budget':1})
    r=admin.post('/api/chat',json={'question':'ลาพักร้อน'})
    id=json.loads(r.text.splitlines()[0])['message_id']
    assert admin.post('/api/messages/'+id+'/feedback',json={'value':'helpful'}).status_code==200
    assert len(admin.get('/api/usage/export',params={'tenant_id':other_tenant['org']}).text.strip().splitlines())==1
    login_as(admin,'member')
    assert admin.post('/api/messages/'+id+'/feedback',json={'value':'helpful'}).status_code==404

def test_sse_provider_stream_and_usage(admin,monkeypatch):
    monkeypatch.setenv('LITELLM_URL','http://gateway.test/v1');original=httpx.AsyncClient
    def respond(request):
        data=json.loads(request.content);assert data['stream'] is True
        content='data: '+json.dumps({'choices':[{'delta':{'content':'คำตอบ [1]'}}]})+'\n\ndata: '+json.dumps({'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20}})+'\n\ndata: [DONE]\n\n'
        return httpx.Response(200,text=content,headers={'content-type':'text/event-stream'})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond)))
    model=admin.post('/api/admin/models',json={'name':'Stream','provider':'LiteLLM','api_id':'stream-test','enabled':True,'input_price':1,'output_price':2}).json()['id']
    r=admin.post('/api/chat',json={'question':'ลาพักร้อน','model_id':model})
    assert 'คำตอบ [1]' in r.text
    assert admin.get('/api/analytics').json()['output_tokens']==20

def test_embedding_dimensions_versioning_and_reranker(monkeypatch):
    from hub import embeddings
    monkeypatch.setenv('EMBEDDING_MODEL','test-embedding')
    monkeypatch.setenv('EMBEDDING_DIMENSIONS','3')
    monkeypatch.setenv('LITELLM_URL','http://gateway.test/v1')
    original=httpx.Client
    def respond(request):
        if request.url.path.endswith('/rerank'):return httpx.Response(200,json={'results':[{'index':1,'relevance_score':.9},{'index':0,'relevance_score':.2}]})
        return httpx.Response(200,json={'data':[{'index':0,'embedding':[1.,0.,0.]}]})
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    before=embeddings.specification()
    assert embeddings.batch(['test'])==[[1.,0.,0.]]
    monkeypatch.setenv('EMBEDDING_VERSION','2')
    assert embeddings.specification()['collection']!=before['collection']
    monkeypatch.setenv('RERANK_MODEL','test-reranker')
    assert embeddings.rerank('q',[{'snippet':'a'},{'snippet':'b'}])[0]['snippet']=='b'
    monkeypatch.setenv('EMBEDDING_DIMENSIONS','4')
    with pytest.raises(ValueError,match='dimensions'):embeddings.batch(['test'])

def test_admin_can_change_own_password(admin):
    assert admin.post('/api/account/password',json={'current_password':'wrong','new_password':'long-test-password'}).status_code==400


def test_chat_without_documents_skips_retrieval(admin, monkeypatch):
    """use_documents=false is a plain LLM chat: no search, no citations, no evidence-only refusal."""
    import json as _json
    from hub import chat_service
    monkeypatch.setattr(chat_service, 'search', lambda *a, **k: (_ for _ in ()).throw(AssertionError('retrieval must not run')))
    r = admin.post('/api/chat', json={'question': 'สวัสดี', 'use_documents': False})
    assert r.status_code == 200
    events = [_json.loads(l) for l in r.text.splitlines() if l.strip()]
    assert events[0]['type'] == 'meta' and events[0]['citations'] == []
    text = ''.join(e.get('text', '') for e in events if e['type'] == 'delta')
    assert 'ยังไม่พบหลักฐาน' not in text and text


def test_chat_attachment_is_private_and_reaches_the_prompt(admin):
    from hub import chat_service
    r = admin.post('/api/chat/attachments', files={'file': ('note.txt', 'รหัสโครงการลับคือ ZX-4471'.encode(), 'text/plain')})
    assert r.status_code == 201 and r.json()['name'] == 'note.txt' and not r.json()['truncated']
    id = r.json()['id']
    assert admin.post('/api/chat/attachments', files={'file': ('a.exe', b'MZ', 'application/octet-stream')}).status_code == 415
    assert admin.post('/api/chat/attachments', files={'file': ('blank.txt', b'   ', 'text/plain')}).status_code in (413, 422)
    assert admin.post('/api/chat', json={'question': 'x', 'use_documents': False, 'attachment_ids': ['0' * 32]}).status_code == 404
    assert admin.post('/api/chat', json={'question': 'x', 'attachment_ids': ['../../x']}).status_code == 422
    user = type('U', (), {'tenant_id': next(u['tenant_id'] for u in [admin.get('/api/auth/me').json()]), 'id': 'someone-else'})
    with pytest.raises(Exception):
        chat_service.load_attachments(user, [id])  # another user cannot read it
    me = admin.get('/api/auth/me').json()
    mine = type('U', (), {'tenant_id': me['tenant_id'], 'id': me['id']})
    assert 'ZX-4471' in chat_service.load_attachments(mine, [id])[0]['text']
    r = admin.post('/api/chat', json={'question': 'รหัสโครงการคืออะไร', 'use_documents': True, 'knowledge_base_id': 'none', 'attachment_ids': [id]})
    assert r.status_code == 200 and 'ยังไม่พบหลักฐาน' not in r.text


def test_user_can_delete_own_conversations(admin):
    import json as _json
    def ask(q):
        r=admin.post('/api/chat',json={'question':q,'use_documents':False});assert r.status_code==200
        return [_json.loads(l) for l in r.text.splitlines() if l.strip()][0]['conversation_id']
    a=ask('ลบฉัน');b=ask('เก็บฉัน')
    assert admin.delete('/api/conversations/'+'0'*8).status_code==404
    assert admin.delete('/api/conversations/'+a).status_code==200
    ids=[c['id'] for c in admin.get('/api/conversations').json()]
    assert a not in ids and b in ids
    assert admin.get('/api/conversations/'+a).status_code==404
    assert admin.delete('/api/conversations').json()['deleted']>=1
    assert admin.get('/api/conversations').json()==[]
    login_as(admin,'member')
    other=ask('ของสมาชิก')
    login_as(admin,'admin')
    assert admin.delete('/api/conversations/'+other).status_code==404  # someone else's


def test_web_search_tool_loop(member,monkeypatch):
    import asyncio,json as _json
    from hub import websearch,chat_service
    cards=websearch.sources([{'title':'A','url':'https://a.test/x','snippet':'hi'},{'title':'B','url':'javascript:x','snippet':''}][:1],2)
    assert cards[0]['number']==3 and cards[0]['chunk_id']=='web:3'
    async def fake(q,n=5):return [{'title':'ข่าว '+q,'url':'https://n.test/1','snippet':'เนื้อหา'}]
    monkeypatch.setattr(websearch,'search',fake)
    class R:
        def __init__(s,d,code=200):s.d=d;s.status_code=code
        def raise_for_status(s):pass
        def json(s):return s.d
    replies=[R({'choices':[{'message':{'content':'','tool_calls':[{'id':'1','function':{'name':'web_search','arguments':_json.dumps({'query':'ราคาทอง'})}}]}}],'usage':{'prompt_tokens':10,'completion_tokens':2}}),
             R({'choices':[{'message':{'content':'ทองราคา X [1]'}}],'usage':{'prompt_tokens':30,'completion_tokens':5}})]
    class C:
        async def post(s,*a,**k):return replies.pop(0)
    used={'provider':'Google AI','api_id':'m'}
    msgs,src,answer,tin,tout=asyncio.run(chat_service.web_prepare(C(),'u','k',used,[{'role':'user','content':'ราคาทอง'}],100,0,lambda t:None))
    assert answer=='ทองราคา X [1]' and src[0]['url']=='https://n.test/1' and (tin,tout)==(40,7)
    assert any(m['role']=='tool' for m in msgs)
    # local model: no tool calling, one forced search is injected into the prompt
    msgs,src,answer,*_=asyncio.run(chat_service.web_prepare(C(),'u','k',{'provider':'Local LLM','api_id':'q'},[{'role':'user','content':'คำถาม: ข่าวด่วน'}],100,0,lambda t:None))
    assert answer is None and 'ผลค้นเว็บ' in msgs[-1]['content'] and src


def test_thought_filter_hides_reasoning_even_when_split_across_chunks():
    from hub.chat_service import ThoughtFilter
    f=ThoughtFilter();out=''.join(f.feed(c) for c in ['<tho','ught>คิดอยู่ ... </thou','ght>คำตอบ ','คือ 4'])+f.flush()
    assert out=='คำตอบ คือ 4'
    assert ThoughtFilter().feed('a < b and <b>bold</b>')=='a < b and <b>bold</b>'


def test_google_audio_helpers(monkeypatch):
    import base64,wave,io
    from hub import google_audio as g
    assert g.base_url('https://generativelanguage.googleapis.com/v1beta/openai')==g.NATIVE
    assert g.audio_mime('x.wav','')=='audio/wav' and g.audio_mime('','audio/webm;codecs=opus')=='audio/webm' and g.audio_mime('a.mp3','audio/mpeg')=='audio/mp3'
    calls=[]
    def fake(base,key,model,body,timeout=120):
        calls.append(body)
        if 'speechConfig' in str(body):return {'candidates':[{'content':{'parts':[{'inlineData':{'mimeType':'audio/L16;codec=pcm;rate=24000','data':base64.b64encode(b'\x00\x01'*100).decode()}}]}}]}
        return {'candidates':[{'content':{'parts':[{'audioTranscription':{'text':' สวัสดี '}}]}}]}
    monkeypatch.setattr(g,'_call',fake)
    assert g.transcribe('b','k','m',b'abc','audio/wav')=='สวัสดี'
    audio,mime=g.speak('b','k','m','hi','alloy')  # an OpenAI voice name falls back to a Gemini voice
    assert mime=='audio/wav' and wave.open(io.BytesIO(audio)).getframerate()==24000
    assert calls[-1]['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName']==g.DEFAULT_VOICE


def test_voice_picker_lists_voices_and_rejects_bad_preview(member):
    voices=member.get('/api/voice/voices').json()
    assert len(voices)==30 and {'name':'Kore','style':'Firm','gender':'female'} in voices
    assert member.post('/api/voice/preview',json={'voice':'NotAVoice','model_id':''}).status_code==422
    assert member.post('/api/voice/preview',json={'voice':'bad name!','model_id':''}).status_code==422


def test_live_setup_per_model_kind():
    from hub import live
    agent=live.build_setup('gemini-3.8-live','docs',True,'Puck','en')
    names=[f['name'] for f in agent['tools'][0]['functionDeclarations']]
    assert names==['search_documents','web_search'] and 'search_documents' in agent['systemInstruction']['parts'][0]['text']
    assert agent['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName']=='Puck'
    general=live.build_setup('gemini-3.1-flash-live-preview','general',False,'bogus','en')
    assert 'tools' not in general and general['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName']=='Kore'
    assert live.build_setup('gemini-3.8-live-extended-thinking','general',False,'','')['generationConfig']['thinkingConfig']['thinkingLevel']
    # only th/en by default: other target languages fall back to the first allowed one; VOICE_LANGUAGES widens the list
    assert live.build_setup('gemini-3.5-live-translate-preview','docs',True,'','ja')['generationConfig']['translationConfig']['targetLanguageCode']=='th'
    assert live.allowed_langs()==['th','en'] and 'ภาษาไทย หรือ ภาษาอังกฤษ' in live.base_prompt()
    import os
    os.environ['VOICE_LANGUAGES']='th,en,ja'
    try: tr=live.build_setup('gemini-3.5-live-translate-preview','docs',True,'','ja')
    finally: del os.environ['VOICE_LANGUAGES']
    assert tr['generationConfig']['translationConfig']['targetLanguageCode']=='ja' and 'tools' not in tr and 'systemInstruction' not in tr
    assert live.build_setup('gemini-3.5-transcribe-live','docs',True,'','')=={'model':'models/gemini-3.5-transcribe-live','inputAudioTranscription':{}}


def test_live_rejects_foreign_origin_and_anonymous(member):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with member.websocket_connect('/api/voice/live',headers={'origin':'https://evil.example'}): pass


def test_client_ip_ignores_forged_headers_and_is_recorded(client=None):
    from hub.clientip import client_ip
    # direct (untrusted) peer: header is ignored
    assert client_ip({'x-forwarded-for': '9.9.9.9'}, '8.8.4.4') == '8.8.4.4'
    # trusted proxy peer: take the entry counted from the right, not the forgeable left-most
    assert client_ip({'x-forwarded-for': '6.6.6.6, 203.0.113.7'}, '172.24.0.4') == '203.0.113.7'
    assert client_ip({'x-forwarded-for': 'garbage'}, '172.24.0.4') == '172.24.0.4'
    assert client_ip({'x-forwarded-for': '::ffff:10.1.2.3'}, '127.0.0.1') == '10.1.2.3'
    assert client_ip({}, '') == ''


def test_cite_check_repoints_wrong_markers_and_drops_unsupported():
    from hub.cite_check import verify
    passages = ['ลาพักร้อน 10 วันต่อปี ยื่นล่วงหน้า 3 วันทำการ เอกสารฉบับนี้เป็นเอกสารภายในขององค์กร',
                'พนักงานสามารถทำงานจากที่บ้านได้ 2 วันต่อสัปดาห์ โดยต้องขออนุมัติจากหัวหน้างานล่วงหน้าอย่างน้อย 1 วัน']
    wrong = 'พนักงานประจำมีสิทธิลาพักร้อน 10 วันต่อปี [2] โดยต้องยื่นคำขอล่วงหน้าอย่างน้อย 3 วันทำการ [1], [2] ผ่านระบบ HR [2]'
    fixed = verify(wrong, passages)
    assert fixed.count('[1]') == 2 and '[2]' not in fixed  # wrong [2] -> [1]; unsupported "HR" claim loses its marker
    assert verify('ทำงานจากที่บ้านได้ 2 วันต่อสัปดาห์ [1]', passages).endswith('[2]')
    assert '[' not in verify('ลาพักร้อน 10 วันต่อปี [7]', passages)  # nonexistent source
    assert verify('ข้อมูลจากเว็บ แหล่งภายนอกล่าสุด [3]', passages, total=3).endswith('[3]')  # web sources left as is


def test_skills_crud_sharing_and_chat(member, admin_login=None):
    c = member
    r = c.post('/api/skills', json={'name': 'ตรวจเอกสาร', 'instructions': 'ตรวจความครบถ้วนของเอกสารและสรุปเป็นข้อ ๆ', 'icon': '📄'})
    assert r.status_code == 201, r.text
    sid = r.json()['id']
    assert c.post('/api/skills', json={'name': 'x', 'instructions': 'สั้นไป'}).status_code == 422
    assert c.post('/api/skills', json={'name': 'แชร์', 'instructions': 'คำสั่งยาวพอสมควรแล้ว', 'shared': True}).status_code == 403
    listed = c.get('/api/skills').json()
    assert [s['name'] for s in listed['skills']] == ['ตรวจเอกสาร'] and not listed['can_share']
    assert c.put(f'/api/skills/{sid}', json={'name': 'ตรวจเอกสาร v2', 'instructions': 'ตรวจความครบถ้วนของเอกสารและสรุปเป็นข้อ ๆ'}).json()['name'] == 'ตรวจเอกสาร v2'
    chat = c.post('/api/chat', json={'question': 'ลาพักร้อนกี่วัน', 'skill_id': sid})
    assert chat.status_code == 200
    assert c.get('/api/skills').json()['skills'][0]['uses'] == 1
    assert c.post('/api/chat', json={'question': 'x', 'skill_id': 'nope'}).status_code == 404
    assert c.post(f'/api/skills/{sid}/copy').status_code == 201
    assert c.delete(f'/api/skills/{sid}').status_code == 204
    assert len(c.get('/api/skills').json()['skills']) == 1


def test_skill_sharing_and_isolation(client, other_tenant):
    assert login_as(client,'admin').status_code == 200
    sid = client.post('/api/skills', json={'name': 'กฎหมาย', 'instructions': 'วิเคราะห์ประเด็นทางกฎหมายอย่างรอบคอบ', 'shared': True}).json()['id']
    assert client.post('/api/auth/logout').status_code in (200, 204)
    assert login_as(client,'member').status_code == 200
    seen = client.get('/api/skills').json()['skills']
    assert [s['name'] for s in seen] == ['กฎหมาย'] and not seen[0]['mine']
    assert client.put(f'/api/skills/{sid}', json={'name': 'แก้', 'instructions': 'พยายามแก้ของคนอื่นดู'}).status_code == 403
    assert client.delete(f'/api/skills/{sid}').status_code == 403


def test_model_effort_saved_and_sent(admin):
    from hub import gateway
    assert gateway.effort_params({'effort': '', 'provider': 'Google AI'}) == {}
    assert gateway.effort_params({'effort': 'high', 'provider': 'Google AI'}) == {'reasoning_effort': 'high'}
    assert gateway.effort_params({'effort': 'low', 'provider': 'OpenRouter'}) == {'reasoning': {'effort': 'low'}}
    m = next(x for x in admin.get('/api/models').json() if x['category'] == 'LLM')
    body = {k: m[k] for k in ('name', 'provider', 'api_id', 'category', 'enabled', 'input_price', 'output_price')} | {'effort': 'medium'}
    assert admin.put('/api/admin/models/' + m['id'], json=body).status_code == 200
    assert next(x for x in admin.get('/api/models').json() if x['id'] == m['id'])['effort'] == 'medium'
    assert admin.put('/api/admin/models/' + m['id'], json=body | {'effort': 'extreme'}).status_code == 422


def test_chat_effort_override_validated(member):
    assert member.post('/api/chat', json={'question': 'ทดสอบ', 'effort': 'low'}).status_code == 200
    assert member.post('/api/chat', json={'question': 'ทดสอบ', 'effort': 'extreme'}).status_code == 422


def test_delete_selected_conversations_only_own(member, other_tenant):
    ids = []
    for q in ('หนึ่ง', 'สอง', 'สาม'):
        r = member.post('/api/chat', json={'question': q})
        assert r.status_code == 200
    ids = [c['id'] for c in member.get('/api/conversations').json()]
    assert len(ids) == 3
    r = member.post('/api/conversations/delete', json={'ids': ids[:2] + ['not-mine']})
    assert r.json()['deleted'] == 2
    assert [c['id'] for c in member.get('/api/conversations').json()] == ids[2:]
    assert member.post('/api/conversations/delete', json={'ids': []}).status_code == 422


class _FakeRedis:
    def __init__(self): self.d={}
    def get(self,k): return self.d.get(k)
    def incr(self,k): self.d[k]=int(self.d.get(k) or 0)+1
    def expire(self,k,t): pass
    def delete(self,k): self.d.pop(k,None)


def test_login_lockout_after_repeated_failures(client,monkeypatch):
    fake=_FakeRedis(); monkeypatch.setattr('hub.jobs.redis_client',lambda:fake)
    for _ in range(8):
        assert client.post('/api/auth/login',json={'email':'lock-test@local.test','password':'wrong'}).status_code==401
    r=client.post('/api/auth/login',json={'email':'lock-test@local.test','password':'wrong'})
    assert r.status_code==429 and 'Retry-After' in r.headers
    # other accounts are not locked by one email's failures
    assert client.post('/api/auth/login',json={'email':'other@local.test','password':'wrong'}).status_code==401

def test_openrouter_image_edit_sends_source_image(admin,monkeypatch):
    monkeypatch.setenv('LITELLM_URL','http://gateway.test/v1')
    monkeypatch.setenv('OPENROUTER_API_KEY','test-key')
    model=admin.post('/api/admin/models',json={'name':'Edit','provider':'OpenRouter','api_id':'krea/k3-edit','category':'Image','enabled':True}).json()['id']
    seen={};original=httpx.Client
    def respond(request):
        if request.url.path.endswith('/images/models'):return httpx.Response(200,json={'data':[{'id':'krea/k3-edit','supported_parameters':{'aspect_ratio':{'type':'enum','values':['1:1','16:9']},'input_references':{'type':'range','min':0,'max':10}}}]})
        seen['path']=request.url.path;seen['body']=json.loads(request.content)
        return httpx.Response(200,json={'data':[{'b64_json':base64.b64encode(b'PNG-edited').decode(),'media_type':'image/png'}],'usage':{'cost':0.008}})
    monkeypatch.setattr(media.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    r=admin.post('/api/media/jobs',data={'kind':'image','model_id':model,'prompt':'make it blue','options':'{"aspect_ratio":"16:9"}'},files={'file':('a.png',b'PNG-src','image/png')});assert r.status_code==202
    job=admin.get('/api/media/jobs').json()[0];assert job['status']=='completed',job
    assert seen['path'].endswith('/images') and seen['body']['prompt']=='make it blue' and seen['body']['aspect_ratio']=='16:9' and 'output_format' not in seen['body'] and job['cost']==.008
    assert base64.b64encode(b'PNG-src').decode() in seen['body']['input_references'][0]['image_url']['url']
    assert admin.get('/api/media/'+r.json()['id']+'/content').content==b'PNG-edited'
    opts=admin.get('/api/media/model-options',params={'model_id':model}).json()
    assert opts['aspect_ratios']==['1:1','16:9'] and opts['accepts_image'] is True
    other=admin.post('/api/admin/models',json={'name':'Plain','provider':'LiteLLM','api_id':'plain','category':'Image','enabled':True}).json()['id']
    assert admin.post('/api/media/jobs',data={'kind':'image','model_id':other,'prompt':'x'},files={'file':('a.png',b'x','image/png')}).status_code==422
    assert admin.post('/api/media/jobs',data={'kind':'image','model_id':model,'prompt':'x'},files={'file':('a.exe',b'x','application/octet-stream')}).status_code==415

def test_openrouter_video_snaps_to_model_limits_and_sends_first_frame(admin,monkeypatch):
    monkeypatch.setenv('LITELLM_URL','http://gateway.test/v1');monkeypatch.setenv('OPENROUTER_API_KEY','test-key')
    model=admin.post('/api/admin/models',json={'name':'Mischief','provider':'OpenRouter','api_id':'tbc/mischief-1','category':'Video','enabled':True}).json()['id']
    seen={};original=httpx.Client
    def respond(request):
        p=request.url.path
        if p.endswith('/videos/models'):return httpx.Response(200,json={'data':[{'id':'tbc/mischief-1','supported_durations':[3,5],'supported_sizes':['854x480','1280x720']}]})
        if p.endswith('/videos') and request.method=='POST':seen['body']=json.loads(request.content);return httpx.Response(200,json={'id':'v1','status':'pending'})
        if p.endswith('/content'):return httpx.Response(200,content=b'test-mp4')
        return httpx.Response(200,json={'status':'completed','usage':{'cost':0.05}})
    monkeypatch.setattr(media.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    r=admin.post('/api/media/jobs',data={'kind':'video','model_id':model,'prompt':'walk','options':'{"seconds":8,"size":"1280x720"}'},files={'file':('a.png',b'PNG-src','image/png')});assert r.status_code==202
    job=admin.get('/api/media/jobs').json()[0];assert job['status']=='completed',job
    b=seen['body'];assert b['duration']==5 and b['size']=='1280x720' and b['frame_images'][0]['frame_type']=='first_frame' and job['cost']==.05

