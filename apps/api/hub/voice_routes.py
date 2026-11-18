"""Voice conversation building blocks: speech-to-text and text-to-speech through the Gateway.

The browser detects speech, sends each utterance to /transcribe, streams the answer from /api/chat (spoken=true)
and asks /speak for audio sentence by sentence, so the answer starts playing before it is finished and the
user can interrupt it at any time.
"""
import re
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from datetime import timedelta
from .database import db_session
from .models import User, Usage
from .auth import current_user
from .policies import choose_model, enforce_user_quota
from . import gateway, savings

router = APIRouter(prefix='/api/voice')
MAX_AUDIO = 10 * 1024 * 1024
SPEAK_LABEL = 'เสียง · พูด'
LISTEN_LABEL = 'เสียง · ถอดเสียง'
BALANCE_MSG = 'ยอดคงเหลือหรือวงเงิน API key ของผู้ให้บริการไม่พอสำหรับงานเสียง (เช่น OpenRouter ต้องมียอดอย่างน้อย $0.50 สำหรับถอดเสียง) ตรวจที่หน้าตั้งค่าของผู้ให้บริการ'
QUOTA_MSG = 'โควตา Google AI ของโมเดลเสียงนี้เต็ม (แพ็กเกจฟรีจำกัดต่อนาที/วัน) แนะนำให้เลือกเอนจิน "สด (Live)" ในหน้านี้แทน'

def guard(db, u, provider=''):
    if not gateway.configured(db, provider): raise HTTPException(503, 'กรุณาตั้งค่า Gateway และ API key ก่อนใช้งานเสียง')
    enforce_user_quota(db, u)
    from .feature_routes import billing
    if billing(u, db)['budget_exceeded']: raise HTTPException(429, 'เกินงบประมาณรายเดือนขององค์กร')

def record(db, u, label, model, response):
    raw = response.headers.get('x-litellm-response-cost')
    try: cost = max(0.0, float(raw)) if raw is not None else None
    except ValueError: cost = None
    db.add(Usage(tenant_id=u.tenant_id, user_id=u.id, model=f'{label} · {model.name}', cost=cost or 0, estimated=cost is None)); db.commit()

@router.post('/transcribe')
async def transcribe(file: UploadFile = File(...), model_id: str = Form(''), language: str = Form('th'), u: User = Depends(current_user), db: Session = Depends(db_session)):
    savings.enforce_limits(db, u, savings.policy(db, u.tenant_id))
    model = choose_model(db, u, 'STT', model_id or None)
    guard(db, u, model.provider)
    data = await file.read(MAX_AUDIO + 1)
    if not data or len(data) > MAX_AUDIO: raise HTTPException(413, 'เสียงต้องไม่ว่างและไม่เกิน 10 MB')
    from .live import allowed_langs
    if language not in allowed_langs(): raise HTTPException(422, 'ภาษานี้ไม่ได้เปิดใช้งานสำหรับเสียง (เปิดใช้: ' + ', '.join(allowed_langs()) + ')')
    url, key = gateway.configuration(db, model.provider)
    if model.provider == 'Google AI':
        from starlette.concurrency import run_in_threadpool
        from . import google_audio
        try: text = await run_in_threadpool(google_audio.transcribe, google_audio.base_url(url), key, model.api_id, data, google_audio.audio_mime(file.filename or '', file.content_type or ''), language)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429: raise HTTPException(429, QUOTA_MSG)
            raise HTTPException(502, 'ถอดเสียงไม่สำเร็จ ตรวจโมเดลถอดเสียงและ API key')
        except (httpx.HTTPError, ValueError, KeyError): raise HTTPException(502, 'ถอดเสียงไม่สำเร็จ ตรวจโมเดลถอดเสียงและ API key')
        db.add(Usage(tenant_id=u.tenant_id, user_id=u.id, model=f'{LISTEN_LABEL} · {model.name}', cost=0, estimated=True)); db.commit()
        return {'text': text}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10), follow_redirects=False) as client:
            name = (file.filename or 'speech.webm').replace('\\', '/').split('/')[-1][:80]  # providers read the audio format from the file name
            r = await client.post(url + '/audio/transcriptions', headers=gateway.headers(key), data={'model': model.api_id, 'language': language}, files={'file': (name, data, file.content_type or 'audio/webm')})
            r.raise_for_status(); text = (r.json().get('text') or '').strip()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 402: raise HTTPException(402, BALANCE_MSG)
        raise HTTPException(502, 'ถอดเสียงไม่สำเร็จ ตรวจโมเดลถอดเสียงและ Gateway')
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, 'ถอดเสียงไม่สำเร็จ ตรวจโมเดลถอดเสียงและ Gateway')
    record(db, u, LISTEN_LABEL, model, r)
    return {'text': text}

@router.get('/voices')
def voices(u: User = Depends(current_user)):
    from .google_audio import VOICES
    from .google_audio import gender_of
    return [{'name': n, 'style': st, 'gender': gender_of(n)} for n, st in VOICES]

@router.get('/languages')
def languages(u: User = Depends(current_user)):
    from .live import allowed_langs, LANG_NAMES
    return [{'code': c, 'name': LANG_NAMES[c]} for c in allowed_langs()]

class PreviewInput(BaseModel):
    voice: str = Field(pattern=r'^[A-Za-z]{2,30}$')
    model_id: str = ''
    live: bool = False

@router.post('/preview')
async def preview(body: PreviewInput, u: User = Depends(current_user), db: Session = Depends(db_session)):
    """A short sample of one Gemini voice. Generated once per model+voice, then served from storage."""
    from starlette.concurrency import run_in_threadpool
    from . import google_audio, storage
    if body.voice not in google_audio.VOICE_NAMES: raise HTTPException(422, 'ไม่รู้จักเสียงนี้')
    from . import live
    model = choose_model(db, u, 'Live' if body.live else 'TTS', body.model_id or None)
    if model.provider != 'Google AI': raise HTTPException(422, 'ตัวอย่างเสียงใช้ได้กับโมเดล Gemini เท่านั้น')
    if body.live and live.kind_of(model.api_id) != 'agent': raise HTTPException(422, 'โมเดลนี้ไม่มีตัวเลือกเสียง')
    guard(db, u, model.provider)
    key = f'{u.tenant_id}/voice-previews/v2/{model.api_id}/{body.voice}.wav'
    text = google_audio.PREVIEW_TEXTS[google_audio.gender_of(body.voice)]
    try: audio = storage.get(key)
    except Exception: audio = b''
    if not audio:
        url, apikey = gateway.configuration(db, model.provider)
        try:
            if body.live: audio = await live.speak_sample(apikey, model.api_id, body.voice, text)
            else: audio, _ = await run_in_threadpool(google_audio.speak, google_audio.base_url(url), apikey, model.api_id, text, body.voice)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429: raise HTTPException(429, 'โควตา Google AI ของโมเดลนี้เต็ม (แพ็กเกจฟรีจำกัดต่อวัน) ลองใหม่ภายหลังหรือเลือกโมเดลอื่น')
            raise HTTPException(502, 'สร้างตัวอย่างเสียงไม่สำเร็จ')
        except HTTPException: raise
        except Exception: raise HTTPException(502, 'สร้างตัวอย่างเสียงไม่สำเร็จ (โควตาหรือการเชื่อมต่อ Live API)')
        if not audio: raise HTTPException(502, 'ผู้ให้บริการไม่ส่งเสียงกลับมา')
        storage.put(key, audio)
        db.add(Usage(tenant_id=u.tenant_id, user_id=u.id, model=f'{SPEAK_LABEL} · ตัวอย่างเสียง · {model.name}', cost=0, estimated=True)); db.commit()
    return Response(content=audio, media_type='audio/wav', headers={'Cache-Control': 'private, max-age=86400'})

class SpeakInput(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    model_id: str = ''
    voice: str = Field(default='alloy', pattern=r'^[A-Za-z0-9_-]{1,40}$')

@router.post('/speak')
async def speak(body: SpeakInput, u: User = Depends(current_user), db: Session = Depends(db_session)):
    recent = db.scalar(select(func.count()).select_from(Usage).where(Usage.user_id == u.id, Usage.model.startswith(SPEAK_LABEL), Usage.created_at >= (savings.utc_now() - timedelta(minutes=1)).isoformat()))
    if recent >= 60: raise HTTPException(429, 'ขอเสียงถี่เกินไป กรุณารอสักครู่')
    model = choose_model(db, u, 'TTS', body.model_id or None)
    guard(db, u, model.provider)
    url, key = gateway.configuration(db, model.provider)
    if model.provider == 'Google AI':
        from starlette.concurrency import run_in_threadpool
        from . import google_audio
        try: audio, mime = await run_in_threadpool(google_audio.speak, google_audio.base_url(url), key, model.api_id, body.text, body.voice)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429: raise HTTPException(429, QUOTA_MSG)
            raise HTTPException(502, 'สร้างเสียงไม่สำเร็จ ตรวจโมเดลอ่านออกเสียงและ API key')
        except (httpx.HTTPError, ValueError, KeyError): raise HTTPException(502, 'สร้างเสียงไม่สำเร็จ ตรวจโมเดลอ่านออกเสียงและ API key')
        if not audio: raise HTTPException(502, 'ผู้ให้บริการไม่ส่งเสียงกลับมา')
        db.add(Usage(tenant_id=u.tenant_id, user_id=u.id, model=f'{SPEAK_LABEL} · {model.name}', cost=0, estimated=True)); db.commit()
        return Response(content=audio, media_type=mime, headers={'Cache-Control': 'no-store'})
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10), follow_redirects=False) as client:
            from . import google_audio
            payload, speech_mime, convert = google_audio.openrouter_speech(model.api_id, body.text, body.voice)
            r = await client.post(url + '/audio/speech', headers=gateway.headers(key), json=payload)
            r.raise_for_status(); audio = convert(r.content) if convert and r.content else r.content
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 402: raise HTTPException(402, BALANCE_MSG)
        raise HTTPException(502, 'สร้างเสียงไม่สำเร็จ ตรวจโมเดลอ่านออกเสียงและ Gateway')
    except httpx.HTTPError:
        raise HTTPException(502, 'สร้างเสียงไม่สำเร็จ ตรวจโมเดลอ่านออกเสียงและ Gateway')
    if not audio: raise HTTPException(502, 'ผู้ให้บริการไม่ส่งเสียงกลับมา')
    record(db, u, SPEAK_LABEL, model, r)
    return Response(content=audio, media_type=speech_mime, headers={'Cache-Control': 'no-store'})
