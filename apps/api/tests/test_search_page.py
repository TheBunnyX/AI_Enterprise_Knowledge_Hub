"""The search page: a list that covers several documents, picture results with a real thumbnail, and the same access rules as the documents."""
import io
import pytest
from PIL import Image, ImageDraw
from sqlalchemy import select
from hub import multimodal, ocr, retrieval
from hub.database import SessionLocal
from hub.models import Chunk
from conftest import login_as
from test_platform import upload


def png():
    image = Image.new('RGB', (320, 240), 'white'); ImageDraw.Draw(image).rectangle((20, 20, 300, 220), outline='black', width=4)
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


@pytest.fixture
def picture(monkeypatch):
    monkeypatch.setenv('MULTIMODAL_RAG', 'true')
    monkeypatch.setattr(ocr, 'image_text', lambda data, suffix='.png': 'ข้อความในภาพ')
    monkeypatch.setattr(multimodal, 'caption', lambda data: 'แผนภาพตารางการทำงานแบบ Hybrid')
    monkeypatch.setattr(multimodal, 'embed_image', lambda data: [1.0, 0.0])
    monkeypatch.setattr(multimodal, 'embed_text', lambda text: [1.0, 0.0])


def picture_chunk_id(client):
    kb = client.get('/api/knowledge-bases').json()[0]
    assert client.put(f"/api/knowledge-bases/{kb['id']}", json={'name': kb['name'], 'description': '', 'multimodal': True}).status_code == 200
    assert client.post('/api/documents', data={'knowledge_base_id': kb['id']}, files={'file': ('chart.png', png(), 'image/png')}).status_code == 201
    with SessionLocal() as db:
        return db.scalar(select(Chunk.id).where(Chunk.kind == 'image'))


def test_a_picture_result_has_a_thumbnail_the_owner_can_open(department, picture):
    id = picture_chunk_id(department)
    r = department.get(f'/api/chunks/{id}/image')
    assert r.status_code == 200 and r.headers['content-type'] == 'image/jpeg' and r.content[:2] == b'\xff\xd8'
    hit = next(x for x in department.get('/api/search', params={'q': 'แผนภาพตารางการทำงาน'}).json() if x['kind'] == 'image')
    assert hit['chunk_id'] == id  # the page builds the thumbnail address from this


def test_the_thumbnail_follows_the_same_access_rules(department, picture, other_tenant):
    id = picture_chunk_id(department)
    assert department.get('/api/chunks/does-not-exist/image').status_code == 404
    with SessionLocal() as db:
        text_chunk = db.scalar(select(Chunk.id).where(Chunk.kind == 'text'))
    assert department.get(f'/api/chunks/{text_chunk}/image').status_code == 404  # only picture chunks have an image
    from fastapi.testclient import TestClient
    from hub.main import app
    with TestClient(app) as anonymous:
        assert anonymous.get(f'/api/chunks/{id}/image').status_code == 401
    with SessionLocal() as db:  # a user of another organisation must not see it either
        from hub.models import User
        user = db.get(User, other_tenant['user'])
        user.password_hash = __import__('hub.auth', fromlist=['passwords']).passwords.hash('testing-password-B'); db.commit()
    with TestClient(app) as b:
        assert b.post('/api/auth/login', json={'email': 'b@example.test', 'password': 'testing-password-B'}).status_code == 200
        assert b.get(f'/api/chunks/{id}/image').status_code == 404


def test_the_list_covers_several_documents_instead_of_one_long_one(department, monkeypatch):
    kb = department.get('/api/knowledge-bases').json()[0]['id']
    long_text = '\n\n'.join(f'ข้อ {i} งบประมาณประจำปีต้องได้รับการอนุมัติจากคณะกรรมการ รายละเอียดข้อที่ {i}' for i in range(30))
    department.post('/api/documents', data={'knowledge_base_id': kb}, files={'file': ('long.txt', long_text.encode(), 'text/plain')})
    department.post('/api/documents', data={'knowledge_base_id': kb}, files={'file': ('short.txt', 'งบประมาณของโครงการต้องแยกบัญชี'.encode(), 'text/plain')})
    hits = department.get('/api/search', params={'q': 'งบประมาณ', 'limit': 6, 'per_doc': 2}).json()
    names = {h['name'] for h in hits}
    assert 'short.txt' in names and 'long.txt' in names
    assert sum(h['name'] == 'long.txt' for h in hits) <= 2  # at most two passages of one document


def test_search_limit_is_bounded(department):
    assert department.get('/api/search', params={'q': 'x', 'limit': 0}).status_code == 422
    assert department.get('/api/search', params={'q': 'x', 'limit': 51}).status_code == 422
    assert department.get('/api/search', params={'q': 'x', 'per_doc': 0}).status_code == 422
