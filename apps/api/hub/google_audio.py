"""Speech-to-text and text-to-speech through Google AI Studio's native generateContent API
(Gemini Transcribe / Gemini TTS). The OpenAI-compatible endpoint does not offer these."""
import base64
import io
import re
import wave
import httpx

NATIVE = 'https://generativelanguage.googleapis.com/v1beta'
DEFAULT_VOICE = 'Kore'
# Prebuilt Gemini TTS voices and their documented character (ai.google.dev/gemini-api/docs/speech-generation).
VOICES = [('Zephyr', 'Bright'), ('Puck', 'Upbeat'), ('Charon', 'Informative'), ('Kore', 'Firm'), ('Fenrir', 'Excitable'), ('Leda', 'Youthful'),
          ('Orus', 'Firm'), ('Aoede', 'Breezy'), ('Callirrhoe', 'Easy-going'), ('Autonoe', 'Bright'), ('Enceladus', 'Breathy'), ('Iapetus', 'Clear'),
          ('Umbriel', 'Easy-going'), ('Algieba', 'Smooth'), ('Despina', 'Smooth'), ('Erinome', 'Clear'), ('Algenib', 'Gravelly'), ('Rasalgethi', 'Informative'),
          ('Laomedeia', 'Upbeat'), ('Achernar', 'Soft'), ('Alnilam', 'Firm'), ('Schedar', 'Even'), ('Gacrux', 'Mature'), ('Pulcherrima', 'Forward'),
          ('Achird', 'Friendly'), ('Zubenelgenubi', 'Casual'), ('Vindemiatrix', 'Gentle'), ('Sadachbia', 'Lively'), ('Sadaltager', 'Knowledgeable'), ('Sulafat', 'Warm')]
VOICE_NAMES = {n for n, _ in VOICES}
# Perceived gender of each voice (Google does not publish this; it is how the voices are generally heard). Used so the
# spoken Thai matches the voice: a male voice says ผม/ครับ, a female voice says ดิฉัน/ค่ะ.
FEMALE = {'Zephyr', 'Kore', 'Leda', 'Aoede', 'Callirrhoe', 'Autonoe', 'Despina', 'Erinome', 'Laomedeia', 'Achernar', 'Gacrux', 'Pulcherrima', 'Vindemiatrix', 'Sulafat'}


def gender_of(voice):
    return 'female' if voice in FEMALE else 'male'


PREVIEW_TEXTS = {'male': 'สวัสดีครับ ยินดีที่ได้รู้จัก นี่คือตัวอย่างเสียงของผม', 'female': 'สวัสดีค่ะ ยินดีที่ได้รู้จัก นี่คือตัวอย่างเสียงของดิฉัน'}
PREVIEW_TEXT = PREVIEW_TEXTS['male']
OPENAI_VOICES = {'alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer', 'ash', 'ballad', 'coral', 'sage', 'verse'}  # names the OpenAI-style UI sends
AUDIO_TYPES = {'mp3': 'audio/mp3', 'wav': 'audio/wav', 'm4a': 'audio/aac', 'aac': 'audio/aac', 'ogg': 'audio/ogg', 'flac': 'audio/flac', 'webm': 'audio/webm', 'mp4': 'audio/mp4'}


def base_url(url):
    """The configured Google URL ends in /openai; the native API is its parent."""
    return (url or NATIVE).rstrip('/').removesuffix('/openai')


def _call(base, key, model, body, timeout=120):
    r = httpx.post(f'{base}/models/{model}:generateContent', headers={'x-goog-api-key': key}, json=body, timeout=httpx.Timeout(timeout, connect=15), follow_redirects=False)
    r.raise_for_status()
    return r.json()


def audio_mime(name='', content_type=''):
    ct = (content_type or '').split(';')[0].strip().lower()
    if ct == 'audio/mpeg':
        return 'audio/mp3'
    if ct.startswith('audio/'):
        return ct
    return AUDIO_TYPES.get(name.rsplit('.', 1)[-1].lower(), 'audio/webm') if name else 'audio/webm'


def _parts(out):
    return ((out.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []


def transcribe(base, key, model, data, mime, language='th'):
    prompt = 'ถอดเสียงพูดเป็นข้อความ' + (' ภาษาไทย' if language == 'th' else f' (รหัสภาษา {language})') + ' ตอบเฉพาะข้อความที่ได้ยิน ไม่ต้องอธิบายเพิ่ม'
    out = _call(base, key, model, {'contents': [{'parts': [{'text': prompt}, {'inlineData': {'mimeType': mime, 'data': base64.b64encode(data).decode()}}]}]})
    return ''.join((p.get('audioTranscription') or {}).get('text') or p.get('text') or '' for p in _parts(out)).strip()


def _wav(pcm, rate=24000):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def speak(base, key, model, text, voice=''):
    name = voice if voice in VOICE_NAMES else DEFAULT_VOICE
    out = _call(base, key, model, {'contents': [{'parts': [{'text': text}]}], 'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': name}}}}})
    inline = next((p.get('inlineData') for p in _parts(out) if p.get('inlineData')), None)
    if not inline:
        return b'', ''
    audio = base64.b64decode(inline['data'])
    mime = inline.get('mimeType', 'audio/wav')
    if mime.startswith('audio/L16') or 'pcm' in mime:  # older TTS models return raw 16-bit PCM
        m = re.search(r'rate=(\d+)', mime)
        return _wav(audio, int(m.group(1)) if m else 24000), 'audio/wav'
    return audio, mime.split(';')[0]
