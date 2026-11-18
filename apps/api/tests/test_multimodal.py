"""Multimodal RAG: pictures are described, embedded, searchable and (for vision models) shown to the answering model."""
import io, json
import httpx
import pytest
from PIL import Image, ImageDraw
from sqlalchemy import select
from hub import multimodal, ocr, storage
from hub.database import SessionLocal
from hub.models import Chunk

CAPTION = 'แผนภาพตารางการทำงานต่อสัปดาห์แบบ Hybrid เข้าสำนักงาน 3 วัน ทำงานที่บ้าน 2 วัน'


def png():
    image = Image.new('RGB', (320, 240), 'white'); ImageDraw.Draw(image).rectangle((20, 20, 300, 220), outline='black', width=4)
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


@pytest.fixture
def pictures(monkeypatch):
    """Multimodal RAG on, with the Google AI calls replaced: the picture's vector is [1, 0], a question about a chart maps to the same direction."""
    monkeypatch.setenv('MULTIMODAL_RAG', 'true')
    monkeypatch.setattr(ocr, 'image_text', lambda data, suffix='.png': '')
    monkeypatch.setattr(multimodal, 'caption', lambda data: CAPTION)
    monkeypatch.setattr(multimodal, 'embed_image', lambda data: [1.0, 0.0])
    monkeypatch.setattr(multimodal, 'embed_text', lambda text: [1.0, 0.0] if 'แผนภาพ' in text or 'chart' in text else [0.0, 1.0])


def first_kb(client):
    return client.get('/api/knowledge-bases').json()[0]


def switch_kb(client, on):
    kb = first_kb(client)
    assert client.put(f"/api/knowledge-bases/{kb['id']}", json={'name': kb['name'], 'description': kb.get('description', ''), 'multimodal': on}).status_code == 200
    return kb['id']


def upload_picture(client, name='chart.png', on=True):
    kb = switch_kb(client, on)  # Multimodal RAG is opt-in per knowledge base
    r = client.post('/api/documents', data={'knowledge_base_id': kb}, files={'file': (name, png(), 'image/png')})
    assert r.status_code == 201, r.text
    return r.json()['id']


def picture_chunks():
    with SessionLocal() as db:
        return db.scalars(select(Chunk).where(Chunk.kind == 'image')).all()


def test_a_picture_becomes_a_chunk_with_description_image_and_vector(department, pictures):
    id = upload_picture(department)
    assert [d['status'] for d in department.get('/api/documents').json() if d['id'] == id] == ['ready']
    chunks = picture_chunks()
    assert len(chunks) == 1
    c = chunks[0]
    assert CAPTION in c.text and c.text.startswith('[ภาพในหน้า 1]')
    assert c.mm_embedding == [1.0, 0.0] and c.embedding  # the picture vector and the ordinary text vector of the description
    assert storage.get(c.image_key)[:2] == b'\xff\xd8'  # the stored JPEG


def test_a_library_that_did_not_opt_in_is_not_sent_to_google(department, pictures):
    upload_picture(department, on=False)  # the global switch is on, this library's is off
    assert picture_chunks() == []


def test_applying_the_switch_reindexes_only_documents_with_pictures(department, pictures, monkeypatch):
    monkeypatch.setattr(ocr, 'image_text', lambda data, suffix='.png': 'ข้อความในภาพ')  # a picture with readable text stays indexable once the switch is off
    kb = upload_picture(department, on=False) and first_kb(department)['id']
    department.post('/api/documents', data={'knowledge_base_id': kb}, files={'file': ('notes.txt', 'ข้อความล้วน'.encode(), 'text/plain')})
    assert picture_chunks() == []
    switch_kb(department, True)
    r = department.post(f'/api/knowledge-bases/{kb}/multimodal/apply')
    assert r.status_code == 200 and r.json() == {'multimodal': True, 'documents': 3, 'reindexed': 2}  # the picture and the seeded sample PDF with a figure; the text file is left alone
    assert len(picture_chunks()) == 2
    assert department.post(f'/api/knowledge-bases/{kb}/multimodal/apply').json()['reindexed'] == 0  # nothing left to do
    switch_kb(department, False)
    assert department.post(f'/api/knowledge-bases/{kb}/multimodal/apply').json() == {'multimodal': False, 'documents': 3, 'reindexed': 2}
    assert picture_chunks() == []  # switching off removes the picture chunks again


def test_a_question_costs_no_picture_embedding_when_nothing_is_indexed(department, pictures, monkeypatch):
    switch_kb(department, True)
    department.post('/api/documents', data={'knowledge_base_id': first_kb(department)['id']}, files={'file': ('a.txt', 'นโยบายลาพักร้อน'.encode(), 'text/plain')})
    def boom(text): raise AssertionError('embedded a question although no picture is indexed')
    monkeypatch.setattr(multimodal, 'embed_text', boom)
    assert department.post('/api/chat', json={'question': 'ลาพักร้อน'}).status_code == 200


def test_nothing_changes_when_multimodal_is_off(department, monkeypatch):
    monkeypatch.setattr(ocr, 'image_text', lambda data, suffix='.png': 'ข้อความในภาพ')
    monkeypatch.delenv('MULTIMODAL_RAG', raising=False)
    upload_picture(department)
    assert picture_chunks() == []


def test_a_picture_is_found_by_meaning_even_without_matching_words(department, pictures):
    upload_picture(department)
    from conftest import login_as
    assert login_as(department, 'member').status_code == 200  # a plain user asks; only department admins upload
    r = department.post('/api/chat', json={'question': 'show me the chart'})
    events = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    meta = next(e for e in events if e['type'] == 'meta')
    assert any(c['kind'] == 'image' and c['name'] == 'chart.png' for c in meta['citations'])
    assert all('image_key' not in c for c in meta['citations'])  # storage keys never reach the browser


def capture(monkeypatch):
    sent = []
    def respond(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'ตอบจากภาพ [1]'}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5}})
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda *a, **kw: real(*a, **{**kw, 'transport': httpx.MockTransport(respond)}))
    return sent


def test_a_vision_model_gets_the_picture_itself(department, pictures, monkeypatch):
    upload_picture(department)
    monkeypatch.setattr(multimodal, 'supports_vision', lambda model: True)
    sent = capture(monkeypatch)
    assert department.post('/api/chat', json={'question': 'show me the chart'}).status_code == 200
    content = sent[-1]['messages'][-1]['content']
    assert isinstance(content, list)
    image = next(p for p in content if p['type'] == 'image_url')
    assert image['image_url']['url'].startswith('data:image/jpeg;base64,')
    assert any('[1] ภาพจาก chart.png หน้า 1' in p.get('text', '') for p in content)


def test_a_text_only_model_gets_the_description_instead(department, pictures, monkeypatch):
    upload_picture(department)
    monkeypatch.setattr(multimodal, 'supports_vision', lambda model: False)
    sent = capture(monkeypatch)
    assert department.post('/api/chat', json={'question': 'show me the chart'}).status_code == 200
    content = sent[-1]['messages'][-1]['content']
    assert isinstance(content, str) and CAPTION in content


def test_reindexing_replaces_the_stored_picture(department, pictures):
    id = upload_picture(department)
    first = picture_chunks()[0].image_key
    assert department.post(f'/api/documents/{id}/reindex').status_code in (200, 202)
    chunks = picture_chunks()
    assert len(chunks) == 1 and chunks[0].image_key != first
    with pytest.raises(Exception):
        storage.get(first)


def test_a_failing_vision_service_does_not_fail_the_document(department, monkeypatch):
    monkeypatch.setenv('MULTIMODAL_RAG', 'true')
    monkeypatch.setattr(ocr, 'image_text', lambda data, suffix='.png': 'ข้อความในภาพ')
    def boom(data): raise RuntimeError('quota')
    monkeypatch.setattr(multimodal, 'caption', boom)
    id = upload_picture(department)
    assert [d['status'] for d in department.get('/api/documents').json() if d['id'] == id] == ['ready']  # the OCR text still indexes
    assert picture_chunks() == []


def test_pdf_pages_with_a_figure_are_picked_out(tmp_path):
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    out = io.BytesIO(); c = canvas.Canvas(out)
    c.drawString(72, 750, 'text only page'); c.showPage()
    c.drawImage(ImageReader(io.BytesIO(png())), 72, 400, 320, 240); c.showPage()
    c.drawString(72, 750, 'text only again'); c.save()
    pages = multimodal.extract('plan.pdf', out.getvalue())
    assert [p for p, _ in pages] == [2] and pages[0][1][:2] == b'\xff\xd8'


def test_with_images_labels_each_picture_with_its_evidence_number():
    messages = [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'คำถาม'}]
    out = multimodal.with_images(messages, [(2, 'a.pdf', 3, 'data:image/jpeg;base64,AAAA')])
    assert messages[-1]['content'] == 'คำถาม'  # the original list is untouched
    assert out[-1]['content'][1]['text'] == '[2] ภาพจาก a.pdf หน้า 3' and out[-1]['content'][2]['type'] == 'image_url'


def test_vision_support_is_decided_per_provider(monkeypatch):
    assert multimodal.supports_vision({'provider': 'Google AI', 'api_id': 'gemini-3.5-flash-lite'})
    assert not multimodal.supports_vision({'provider': 'Google AI', 'api_id': 'gemma-4-31b-it'.replace('gemma', 'text')})
    assert not multimodal.supports_vision({'provider': 'Local LLM', 'api_id': 'qwen3.5-2b'})
    monkeypatch.setattr(multimodal, '_openrouter_vision', lambda: {'google/gemini-3.5-flash-lite'})
    assert multimodal.supports_vision({'provider': 'OpenRouter', 'api_id': 'google/gemini-3.5-flash-lite'})
    assert not multimodal.supports_vision({'provider': 'OpenRouter', 'api_id': 'deepseek/deepseek-v4.1-flash-1017'})
