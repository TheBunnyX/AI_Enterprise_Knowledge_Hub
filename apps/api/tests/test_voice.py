from sqlalchemy import select
from hub import gateway
from hub import voice_routes as v
from hub.database import SessionLocal
from hub.models import AIModel, Usage

class Resp:
    def __init__(self, content=b'', js=None, cost='0.002'):
        self.content = content; self._js = js or {}; self.headers = {'x-litellm-response-cost': cost}
    def raise_for_status(self): pass
    def json(self): return self._js

def fake_client(calls, fail=False):
    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None, data=None, files=None):
            calls.append((url, json or data))
            if fail: raise v.httpx.ConnectError('down')
            return Resp(js={'text': ' สวัสดีครับ '}) if url.endswith('transcriptions') else Resp(content=b'ID3audio')
    return Client

def setup(monkeypatch):
    monkeypatch.setattr(gateway, 'configuration', lambda db=None, provider='': ('http://gateway.test', 'k'))
    with SessionLocal() as db:
        db.add_all([AIModel(name='stt', provider='X', api_id='x/stt', category='STT', enabled=True), AIModel(name='tts', provider='X', api_id='x/tts', category='TTS', enabled=True)]); db.commit()

def test_transcribe_and_speak_record_usage(admin, monkeypatch):
    setup(monkeypatch); calls = []
    monkeypatch.setattr(v.httpx, 'AsyncClient', fake_client(calls))
    r = admin.post('/api/voice/transcribe', files={'file': ('a.webm', b'xx', 'audio/webm')}, data={'language': 'th'})
    assert r.status_code == 200 and r.json() == {'text': 'สวัสดีครับ'}
    s = admin.post('/api/voice/speak', json={'text': 'สวัสดี'})
    assert s.status_code == 200 and s.content == b'ID3audio' and s.headers['content-type'] == 'audio/mpeg'
    assert calls[0][1]['model'] == 'x/stt' and calls[1][1]['model'] == 'x/tts'
    with SessionLocal() as db:
        names = [u.model for u in db.scalars(select(Usage))]
        assert any(n.startswith('เสียง · ถอดเสียง') for n in names) and any(n.startswith('เสียง · พูด') for n in names)

def test_validation_and_failures(admin, monkeypatch):
    setup(monkeypatch)
    assert admin.post('/api/voice/transcribe', files={'file': ('a.webm', b'', 'audio/webm')}).status_code == 413
    assert admin.post('/api/voice/transcribe', files={'file': ('a.webm', b'x', 'audio/webm')}, data={'language': '../x'}).status_code == 422
    assert admin.post('/api/voice/speak', json={'text': ''}).status_code == 422
    assert admin.post('/api/voice/speak', json={'text': 'a', 'voice': '../x'}).status_code == 422
    monkeypatch.setattr(v.httpx, 'AsyncClient', fake_client([], fail=True))
    assert admin.post('/api/voice/speak', json={'text': 'a'}).status_code == 502
    assert admin.post('/api/voice/transcribe', files={'file': ('a.webm', b'x', 'audio/webm')}).status_code == 502

def test_requires_login(client):
    assert client.post('/api/voice/speak', json={'text': 'a'}).status_code in (401, 403)

def test_my_quota_endpoint(admin):
    r = admin.get('/api/me/quota')
    assert r.status_code == 200 and set(r.json()) == {'monthly_budget', 'month_spend'}
