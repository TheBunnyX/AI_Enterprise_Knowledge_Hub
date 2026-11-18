"""Multimodal RAG: pictures become searchable and can be shown to a vision model.

Level 1  Each picture (a standalone image, or a PDF page that contains a figure) is described by a vision model. The description
         is stored as an ordinary chunk with kind='image', so BM25, the text embedding and the reranker find it like any text.
Level 2  The picture itself is embedded with a multimodal embedding model that shares one vector space with text. Search adds that
         ranking (query text against picture vectors) to the BM25 and text-vector rankings before fusion.
Level 3  When the answering model can see images, the best picture chunks are sent to it with the evidence, so it can read charts
         and diagrams instead of relying on a description.

Off unless MULTIMODAL_RAG=true: pictures and the text of questions are sent to Google AI. Needs a Google AI key (GOOGLE_AI_API_KEY or
the key saved for the Google AI provider)."""
import base64, io, logging, math, os, time
import httpx

log = logging.getLogger('hub.multimodal')
MAX_SIDE = 1600
MIN_PIXELS = 150 * 150  # smaller pictures are logos and icons
CAPTION_PROMPT = ('อธิบายภาพนี้เป็นภาษาไทยเพื่อใช้ค้นหาเอกสาร: บอกว่าเป็นภาพอะไร (กราฟ แผนภาพ ตาราง รูปถ่าย หน้าเอกสารสแกน) '
                  'อ่านข้อความ ป้ายกำกับ หัวข้อ และตัวเลขทั้งหมดที่เห็นให้ตรงตามภาพ สรุปสิ่งที่ภาพสื่อ ห้ามเดาสิ่งที่ไม่เห็นในภาพ')


def enabled():
    return os.getenv('MULTIMODAL_RAG', '').strip().lower() in ('1', 'true', 'yes', 'on')


def settings():
    return {'caption_model': os.getenv('MM_CAPTION_MODEL', 'gemini-3.5-flash-lite'), 'embed_model': os.getenv('MM_EMBED_MODEL', 'gemini-embedding-2'),
            'dims': int(os.getenv('MM_EMBED_DIMS', '768')), 'max_images': int(os.getenv('MM_MAX_IMAGES', '12')),
            'min_score': float(os.getenv('MM_MIN_SCORE', '0.38')), 'answer_images': int(os.getenv('MM_ANSWER_IMAGES', '2'))}


def collection():
    s = settings()
    return 'hub_mm_' + ''.join(c if c.isalnum() else '_' for c in s['embed_model']) + '_' + str(s['dims'])


def _google():
    """(OpenAI-compatible base URL, native API base URL, key) of the Google AI provider."""
    from . import gateway
    url, key = gateway.configuration(None, 'Google AI')
    if not key: raise RuntimeError('ยังไม่ได้ตั้งค่า API key ของ Google AI (ใช้กับ Multimodal RAG)')
    return url, url.removesuffix('/openai'), key


def _post(url, headers, body, tries=3):
    for i in range(tries):
        r = httpx.post(url, headers=headers, json=body, timeout=90)
        if r.status_code in (429, 500, 502, 503, 504) and i < tries - 1:
            time.sleep(2 * (i + 1)); continue
        r.raise_for_status(); return r.json()


# ---------- pictures out of documents ----------
def jpeg(image):
    image = image.convert('RGB'); w, h = image.size; scale = MAX_SIDE / max(w, h)
    if scale < 1: image = image.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    out = io.BytesIO(); image.save(out, 'JPEG', quality=82); return out.getvalue()


def _has_picture(page):
    try:
        return any(img.image.size[0] * img.image.size[1] >= MIN_PIXELS for img in page.images)
    except Exception:
        return False  # a page whose images cannot be read is indexed as text only


def extract(name, data):
    """[(page, jpeg bytes)] for the pictures of one file: the image itself, or each PDF page that contains a figure."""
    ext = name.rsplit('.', 1)[-1].lower(); cap = settings()['max_images']
    if ext in ('png', 'jpg', 'jpeg'):
        from PIL import Image
        image = Image.open(io.BytesIO(data)); image.load(); return [(1, jpeg(image))]
    if ext == 'pdf':
        from pypdf import PdfReader
        pages = []
        for i, page in enumerate(PdfReader(io.BytesIO(data)).pages):
            if len(pages) >= cap: break
            if _has_picture(page): pages.append(i)
        if not pages: return []
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(data)
        try: return [(i + 1, jpeg(pdf[i].render(scale=1.5).to_pil())) for i in pages]
        finally: pdf.close()
    return []


def contains_pictures(name, data):
    """Cheap check (no rendering, no network): does this file have a picture worth describing? Used to re-index only those documents."""
    ext = name.rsplit('.', 1)[-1].lower()
    if ext in ('png', 'jpg', 'jpeg'): return True
    if ext != 'pdf': return False
    from pypdf import PdfReader
    return any(_has_picture(p) for p in PdfReader(io.BytesIO(data)).pages)


# ---------- level 1: description, level 2: vectors ----------
def caption(data):
    base, _, key = _google()
    body = {'model': settings()['caption_model'], 'max_tokens': 900, 'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': CAPTION_PROMPT}, {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(data).decode()}}]}]}
    text = _post(base + '/chat/completions', {'Authorization': 'Bearer ' + key}, body)['choices'][0]['message']['content']
    return (text or '').strip()[:1500]


def _embed(parts):
    _, native, key = _google(); s = settings()
    values = _post(f"{native}/models/{s['embed_model']}:embedContent", {'x-goog-api-key': key}, {'content': {'parts': parts}, 'outputDimensionality': s['dims']})['embedding']['values']
    norm = math.sqrt(sum(v * v for v in values)) or 1
    return [v / norm for v in values]


def embed_image(data): return _embed([{'inlineData': {'mimeType': 'image/jpeg', 'data': base64.b64encode(data).decode()}}])
def embed_text(text): return _embed([{'text': text[:2000]}])


def index_pictures(name, data):
    """[(page, jpeg, description, vector)] for the pictures of a file. A picture that fails is skipped, never the whole document."""
    out = []
    for page, picture in extract(name, data):
        try:
            description = caption(picture)
            if not description: continue
            out.append((page, picture, description, embed_image(picture)))
        except Exception as e:
            log.warning('multimodal: picture on page %s of %s skipped: %s', page, name, e.__class__.__name__)
    return out


# ---------- level 3: show the pictures to the answering model ----------
_vision = {'at': 0.0, 'ids': set()}


def _openrouter_vision():
    if _vision['ids'] and time.time() - _vision['at'] < 600: return _vision['ids']
    try:
        data = httpx.get('https://openrouter.ai/api/v1/models', timeout=15).json()['data']
        _vision.update(at=time.time(), ids={m['id'].lower() for m in data if 'image' in (m.get('architecture') or {}).get('input_modalities', [])})
    except Exception:
        _vision['at'] = time.time()  # keep the old list and do not retry on every question
    return _vision['ids']


def supports_vision(model):
    """model: the chat snapshot ({'provider','api_id'}). Local models and unknown providers get the text description only."""
    api_id = (model.get('api_id') or '').lower(); provider = model.get('provider')
    if provider == 'Google AI': return api_id.startswith('gemini')
    if provider == 'OpenRouter': return api_id in _openrouter_vision()
    return False


def image_refs(db, found, limit=None):
    """[(number, name, page, storage key)] for the picture chunks among the retrieved passages, best first."""
    from sqlalchemy import select
    from .models import Chunk
    ids = [r['chunk_id'] for r in found if r.get('kind') == 'image']
    if not ids: return []
    keys = {c.id: c.image_key for c in db.scalars(select(Chunk).where(Chunk.id.in_(ids))) if c.image_key}
    out = [(i + 1, r['name'], r['page'], keys[r['chunk_id']]) for i, r in enumerate(found) if r['chunk_id'] in keys]
    return out[:limit or settings()['answer_images']]


def load_images(refs):
    from . import storage
    out = []
    for number, name, page, key in refs:
        try: out.append((number, name, page, 'data:image/jpeg;base64,' + base64.b64encode(storage.get(key)).decode()))
        except Exception: log.warning('multimodal: picture %s could not be read', key)
    return out


def with_images(messages, images):
    """The last (user) message as text + labelled images. [n] matches the numbered evidence in the text."""
    last = dict(messages[-1])
    parts = [{'type': 'text', 'text': str(last['content']) + '\n\nภาพประกอบหลักฐาน (หมายเลข [n] ตรงกับหลักฐานข้างบน ให้ดูภาพจริงก่อนตอบ และอ้างหมายเลขเดิม):'}]
    for number, name, page, url in images:
        parts += [{'type': 'text', 'text': f'[{number}] ภาพจาก {name} หน้า {page}'}, {'type': 'image_url', 'image_url': {'url': url}}]
    last['content'] = parts
    return messages[:-1] + [last]
