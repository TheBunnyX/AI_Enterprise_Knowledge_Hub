"""Gemini Live API relay for the voice page.

The browser streams 16 kHz PCM to this WebSocket; the server forwards it to Google's Live API (so the API key never
reaches the browser), runs tool calls (document search / web search) with the caller's own permissions, and sends
24 kHz PCM audio plus transcripts back.

Browser -> server: binary = 16-bit mono PCM @16 kHz;  text JSON {"type":"text","text":"..."} | {"type":"stop"}
Server -> browser: binary = 16-bit mono PCM @24 kHz;  text JSON events: ready, transcript, turn, interrupted, tool, sources, status, error
"""
import asyncio
import base64
import json
import time
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from .database import SessionLocal, scope_to_tenant
from .models import Usage
from .auth import current_user
from .policies import choose_model, enforce_user_quota
from . import gateway, savings, websearch

router = APIRouter()
LIVE_URL = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent'
LIVE_LABEL = 'เสียง · สด (Live)'
MAX_SECONDS = 15 * 60
ACTIVE = set()  # one live session per user: sessions are billed per audio second
LANG_NAMES = {'th': 'ไทย', 'en': 'อังกฤษ', 'ja': 'ญี่ปุ่น', 'ko': 'เกาหลี', 'zh': 'จีน', 'es': 'สเปน', 'fr': 'ฝรั่งเศส', 'de': 'เยอรมัน', 'it': 'อิตาลี', 'pt': 'โปรตุเกส',
              'ru': 'รัสเซีย', 'ar': 'อาหรับ', 'hi': 'ฮินดี', 'id': 'อินโดนีเซีย', 'vi': 'เวียดนาม', 'ms': 'มาเลย์', 'tr': 'ตุรกี', 'pl': 'โปแลนด์', 'nl': 'ดัตช์'}
LANGS = set(LANG_NAMES)


def allowed_langs():
    """Languages the voice features may use, from VOICE_LANGUAGES (comma separated codes, default th,en)."""
    import os
    codes = [c.strip().lower() for c in os.getenv('VOICE_LANGUAGES', 'th,en').split(',')]
    ok = [c for c in dict.fromkeys(codes) if c in LANGS]
    return ok or ['th', 'en']

def base_prompt(voice=''):
    from .google_audio import gender_of, DEFAULT_VOICE
    langs = allowed_langs()
    names = ' หรือ '.join('ภาษา' + LANG_NAMES[c] for c in langs)
    return ('คุณคือผู้ช่วย AI ขององค์กรที่คุยกับผู้ใช้ด้วยเสียง ตอบเป็น' + names + 'เท่านั้น ตามภาษาที่ผู้ใช้พูด ถ้าไม่แน่ใจให้ใช้ภาษา' + LANG_NAMES[langs[0]] + ' ตอบสั้น กระชับ เป็นธรรมชาติแบบการพูด '
            'ห้ามอ่านสัญลักษณ์ markdown ลิงก์ หรือรายการยาว ๆ ให้สรุปเป็นประโยคพูด'
            + (' เสียงของคุณเป็นผู้ชาย เมื่อพูดภาษาไทยให้เรียกตัวเองว่า "ผม" และลงท้ายด้วย "ครับ" เสมอ ห้ามใช้ "ค่ะ" "คะ" "ดิฉัน" "หนู" แม้แต่ครั้งเดียว'
               if gender_of(voice or DEFAULT_VOICE) == 'male' else
               ' เสียงของคุณเป็นผู้หญิง เมื่อพูดภาษาไทยให้เรียกตัวเองว่า "ดิฉัน" และลงท้ายด้วย "ค่ะ" หรือ "คะ" เสมอ ห้ามใช้ "ครับ" "ผม" แม้แต่ครั้งเดียว'))
DOCS_PROMPT = ' ทุกครั้งที่ผู้ใช้ถามข้อมูลขององค์กร ต้องเรียก search_documents ก่อนตอบ แล้วตอบจากผลที่ได้เท่านั้นและบอกชื่อเอกสารที่ใช้ ถ้าไม่พบให้บอกตรง ๆ ว่าไม่พบในเอกสาร ห้ามเดา'
WEB_PROMPT = ' เมื่อต้องการข้อมูลล่าสุดหรือข้อมูลจากอินเทอร์เน็ต ให้เรียก web_search แล้วสรุปให้ฟัง'
GENERAL_PROMPT = ' ตอบจากความรู้ทั่วไปของคุณ ไม่ต้องค้นเอกสารขององค์กร'


def _tool(name, description):
    return {'name': name, 'description': description, 'parameters': {'type': 'OBJECT', 'properties': {'query': {'type': 'STRING', 'description': 'คำค้นหา'}}, 'required': ['query']}}


def kind_of(api_id):
    return 'translate' if 'translate' in api_id else 'transcribe' if 'transcribe' in api_id else 'agent'


def build_setup(api_id, mode, web, voice, lang):
    """The setup message differs a lot between agent, translation and transcription models."""
    kind = kind_of(api_id)
    setup = {'model': 'models/' + api_id}
    if kind == 'transcribe':
        setup['inputAudioTranscription'] = {}
        return setup
    setup['generationConfig'] = {'responseModalities': ['AUDIO']}
    setup['inputAudioTranscription'] = {}
    setup['outputAudioTranscription'] = {}
    if kind == 'translate':
        setup['generationConfig']['translationConfig'] = {'targetLanguageCode': lang if lang in allowed_langs() else allowed_langs()[0]}
        return setup
    from .google_audio import VOICE_NAMES, DEFAULT_VOICE
    chosen = voice if voice in VOICE_NAMES else DEFAULT_VOICE
    setup['generationConfig']['speechConfig'] = {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': chosen}}}
    if 'extended-thinking' in api_id:
        setup['generationConfig']['thinkingConfig'] = {'thinkingLevel': 'low'}
    tools = []
    if mode == 'docs':
        tools.append(_tool('search_documents', 'ค้นหาข้อมูลจากเอกสารและคลังความรู้ขององค์กรที่ผู้ใช้มีสิทธิ์เห็น'))
    if web:
        tools.append(_tool('web_search', 'ค้นหาข้อมูลล่าสุดจากอินเทอร์เน็ต'))
    setup['systemInstruction'] = {'parts': [{'text': base_prompt(chosen) + (DOCS_PROMPT if mode == 'docs' else GENERAL_PROMPT) + (WEB_PROMPT if web else '')}]}
    if tools:
        setup['tools'] = [{'functionDeclarations': tools}]
    return setup


async def speak_sample(key, api_id, voice, text):
    """Read `text` aloud with this Live model and voice; returns a 24 kHz WAV. Used for voice previews."""
    import websockets
    from .google_audio import _wav
    setup = build_setup(api_id, 'general', False, voice, 'en')
    setup['systemInstruction'] = {'parts': [{'text': 'อ่านข้อความที่ผู้ใช้ส่งมาให้ตรงตามตัวอักษรเท่านั้น ห้ามเพิ่ม ห้ามตอบ ห้ามทักทายเพิ่ม'}]}
    pcm = bytearray()
    async with websockets.connect(LIVE_URL, additional_headers={'x-goog-api-key': key}, max_size=None, open_timeout=15) as g:
        await g.send(json.dumps({'setup': setup}))
        if 'setupComplete' not in json.loads(await asyncio.wait_for(g.recv(), 20)):
            raise RuntimeError('setup failed')
        await g.send(json.dumps({'realtimeInput': {'text': text}}))
        async def collect():
            async for raw in g:
                sc = json.loads(raw).get('serverContent') or {}
                for p in (sc.get('modelTurn') or {}).get('parts', []):
                    if p.get('inlineData'):
                        pcm.extend(base64.b64decode(p['inlineData']['data']))
                if sc.get('turnComplete') or sc.get('generationComplete'):
                    return
        await asyncio.wait_for(collect(), 40)
    return _wav(bytes(pcm)) if pcm else b''


def _docs(user_id, tenant_id, kb, query):
    from .retrieval import search
    from .models import User
    db = SessionLocal()
    try:
        scope_to_tenant(db, tenant_id)
        u = db.get(User, user_id)
        found = search(db, tenant_id, query, kb or None, [], limit=4, user=u)
        if not found:
            found = search(db, tenant_id, query, kb or None, [], limit=3, user=u, relaxed=True)
        return [{'name': r['name'], 'page': r['page'], 'text': r['snippet'][:900]} for r in found]
    finally:
        db.close()


async def run_tool(name, query, ctx, send):
    query = str(query or '')[:300]
    if name == 'search_documents' and ctx['mode'] == 'docs':
        await send({'type': 'tool', 'text': 'กำลังค้นเอกสาร: ' + query})
        found = await run_in_threadpool(_docs, ctx['user_id'], ctx['tenant_id'], ctx['kb'], query)
        await send({'type': 'sources', 'items': [{'name': f['name'], 'page': f['page']} for f in found]})
        return {'results': found} if found else {'results': [], 'note': 'ไม่พบในเอกสาร'}
    if name == 'web_search' and ctx['web']:
        await send({'type': 'tool', 'text': 'กำลังค้นเว็บ: ' + query})
        found = await websearch.search(query)
        await send({'type': 'sources', 'items': [{'name': f.get('title', ''), 'url': f.get('url', '')} for f in found]})
        return {'results': [{'title': f.get('title', ''), 'url': f.get('url', ''), 'text': (f.get('snippet') or '')[:500]} for f in found]}
    return {'error': 'ไม่รองรับเครื่องมือนี้'}


def same_origin(ws: WebSocket):
    origin = ws.headers.get('origin')
    # behind the web container's proxy the original host arrives in X-Forwarded-Host
    host = ws.headers.get('x-forwarded-host') or ws.headers.get('host', '')
    return not origin or urlparse(origin).netloc == host


@router.websocket('/api/voice/live')
async def live(ws: WebSocket):
    if not same_origin(ws):
        await ws.close(4403)
        return
    q = ws.query_params
    db = SessionLocal()
    ctx = None
    try:
        u = current_user(ws, db)  # reads only the session cookie
        model = choose_model(db, u, 'Live', q.get('model_id') or None)
        if model.provider != 'Google AI':
            raise HTTPException(422, 'โหมดสดรองรับเฉพาะโมเดลจาก Google AI')
        if not gateway.configured(db, model.provider):
            raise HTTPException(503, 'ยังไม่ได้ตั้งค่า API key ของ Google AI')
        enforce_user_quota(db, u)
        savings.enforce_limits(db, u, savings.policy(db, u.tenant_id))
        from .feature_routes import billing
        if billing(u, db)['budget_exceeded']:
            raise HTTPException(429, 'เกินงบประมาณรายเดือนขององค์กร')
        url, key = gateway.configuration(db, model.provider)
        ctx = {'user_id': u.id, 'tenant_id': u.tenant_id, 'api_id': model.api_id, 'model_name': model.name, 'kb': q.get('kb') or '', 'mode': 'docs' if q.get('mode', 'docs') == 'docs' else 'general', 'web': q.get('web') == '1' and savings.policy(db, u.tenant_id)['web_search'] != 'off'}
        setup = build_setup(model.api_id, ctx['mode'], ctx['web'], q.get('voice', ''), q.get('lang', 'en'))
    except HTTPException as e:
        await ws.accept()
        await ws.send_text(json.dumps({'type': 'error', 'message': e.detail}, ensure_ascii=False))
        await ws.close(4400 if e.status_code != 401 else 4401)
        return
    finally:
        db.close()
    if ctx['user_id'] in ACTIVE:
        await ws.accept()
        await ws.send_text(json.dumps({'type': 'error', 'message': 'มีการสนทนาเสียงสดที่เปิดอยู่แล้ว กรุณาปิดก่อน'}, ensure_ascii=False))
        await ws.close(4409)
        return
    ACTIVE.add(ctx['user_id'])
    await ws.accept()
    tokens = {'in': 0, 'out': 0}
    started = time.time()

    async def send(event):
        await ws.send_text(json.dumps(event, ensure_ascii=False))

    try:
        import websockets
        async with websockets.connect(LIVE_URL, additional_headers={'x-goog-api-key': key}, max_size=None, open_timeout=15) as g:
            await g.send(json.dumps({'setup': setup}))
            first = json.loads(await asyncio.wait_for(g.recv(), 20))
            if 'setupComplete' not in first:
                raise RuntimeError('เริ่มเซสชันไม่สำเร็จ')
            await send({'type': 'ready', 'kind': kind_of(model.api_id)})

            async def upstream():  # browser -> Google
                while time.time() - started < MAX_SECONDS:
                    msg = await ws.receive()
                    if msg['type'] == 'websocket.disconnect':
                        return
                    if msg.get('bytes'):
                        await g.send(json.dumps({'realtimeInput': {'audio': {'data': base64.b64encode(msg['bytes']).decode(), 'mimeType': 'audio/pcm;rate=16000'}}}))
                    elif msg.get('text'):
                        try:
                            ev = json.loads(msg['text'])
                        except ValueError:
                            continue
                        if ev.get('type') == 'stop':
                            return
                        if ev.get('type') == 'text' and ev.get('text') and kind_of(model.api_id) == 'agent':
                            await g.send(json.dumps({'realtimeInput': {'text': str(ev['text'])[:2000]}}))
                await send({'type': 'status', 'text': 'ครบเวลาสูงสุดของเซสชัน 15 นาที'})

            async def downstream():  # Google -> browser
                async for raw in g:
                    m = json.loads(raw)
                    meta = m.get('usageMetadata')
                    if meta:
                        tokens['in'] += meta.get('promptTokenCount', 0)
                        tokens['out'] += meta.get('responseTokenCount', 0)
                    if m.get('goAway'):
                        await send({'type': 'status', 'text': 'เซสชันใกล้หมดเวลา'})
                    tc = m.get('toolCall')
                    if tc:
                        replies = []
                        for fc in tc.get('functionCalls', []):
                            result = await run_tool(fc.get('name'), (fc.get('args') or {}).get('query'), ctx, send)
                            replies.append({'id': fc.get('id'), 'name': fc.get('name'), 'response': result})
                        await g.send(json.dumps({'toolResponse': {'functionResponses': replies}}))
                    sc = m.get('serverContent')
                    if not sc:
                        continue
                    for part in (sc.get('modelTurn') or {}).get('parts', []):
                        inline = part.get('inlineData')
                        if inline and inline.get('data'):
                            await ws.send_bytes(base64.b64decode(inline['data']))
                    if sc.get('inputTranscription', {}).get('text'):
                        await send({'type': 'transcript', 'role': 'user', 'text': sc['inputTranscription']['text']})
                    if sc.get('outputTranscription', {}).get('text'):
                        await send({'type': 'transcript', 'role': 'ai', 'text': sc['outputTranscription']['text']})
                    if sc.get('interrupted'):
                        await send({'type': 'interrupted'})
                    if sc.get('turnComplete'):
                        await send({'type': 'turn'})

            tasks = [asyncio.create_task(upstream()), asyncio.create_task(downstream())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            ACTIVE.discard(ctx['user_id'])  # free the slot now so end -> start works without waiting for the close handshake
            for t in done:
                if t.exception() and not isinstance(t.exception(), (WebSocketDisconnect, asyncio.CancelledError)):
                    raise t.exception()
    except Exception as e:  # noqa: BLE001 - tell the browser, never leak Google's raw error text with the key
        name = type(e).__name__
        text = str(e)
        reason = 'โควตาของ Google AI เต็ม ลองใหม่ภายหลัง' if '429' in text or 'quota' in text.lower() else 'การเชื่อมต่อเสียงสดขัดข้อง (' + name + ')'
        try:
            await send({'type': 'error', 'message': reason})
        except Exception:  # noqa: BLE001
            pass
    finally:
        ACTIVE.discard(ctx['user_id'])
        db = SessionLocal()
        try:
            scope_to_tenant(db, ctx['tenant_id'])
            db.add(Usage(tenant_id=ctx['tenant_id'], user_id=ctx['user_id'], model=f"{LIVE_LABEL} · {ctx['model_name']}", provider='Google AI', input_tokens=tokens['in'], output_tokens=tokens['out'], cost=0, estimated=True))
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        finally:
            db.close()
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass
