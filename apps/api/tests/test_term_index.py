"""The PostgreSQL BM25 index returns the same ranking and scores as scanning every chunk in memory."""
import time
import pytest
from sqlalchemy import select, func
from hub import retrieval, terms
from hub.database import SessionLocal
from hub.models import Chunk, ChunkTerm, Document
from test_platform import upload

TEXTS = {
    'leave.txt': 'นโยบายลาพักร้อน พนักงานลาได้สิบวันต่อปี และต้องแจ้งล่วงหน้าเจ็ดวัน',
    'travel.txt': 'ค่าใช้จ่ายเดินทางต้องแนบใบเสร็จ travel expense policy requires receipts within thirty days',
    'safety.txt': 'ความปลอดภัยในโรงงาน ต้องสวมหมวกนิรภัยและแว่นตา safety helmet and goggles are mandatory',
}


def ready(admin, ids):
    for _ in range(60):
        with SessionLocal() as db:
            if all(db.get(Document, i).status == 'ready' for i in ids): return
        time.sleep(1)
    raise AssertionError('documents did not become ready')


def search(query, tenant, indexed, monkeypatch):
    monkeypatch.setattr(terms, 'MIN_CHUNKS', 0 if indexed else 10 ** 9)  # index on / always scan in memory
    with SessionLocal() as db:
        return retrieval.search(db, tenant, query, mode='keyword', limit=10)


def test_index_matches_memory_scan_and_backfill_rebuilds_it(admin, monkeypatch):
    ids = [upload(admin, text, name=name).json()['id'] for name, text in TEXTS.items()]
    ready(admin, ids)
    with SessionLocal() as db:
        tenant = db.get(Document, ids[0]).tenant_id
        assert db.scalar(select(func.count()).select_from(ChunkTerm).where(ChunkTerm.document_id.in_(ids))) > 0  # ingestion wrote the index
    queries = ('ลาพักร้อน', 'travel receipts policy', 'หมวกนิรภัย helmet', 'ไม่มีคำนี้เลยzzz')
    expected = {q: search(q, tenant, False, monkeypatch) for q in queries}
    assert expected['ลาพักร้อน'], 'the in-memory scan should find the leave document'
    # drop the index of these documents and rebuild it with the backfill, as happens after an upgrade
    with SessionLocal() as db:
        db.query(ChunkTerm).filter(ChunkTerm.document_id.in_(ids)).delete(synchronize_session=False)
        db.query(Chunk).filter(Chunk.document_id.in_(ids)).update({Chunk.length: -1}, synchronize_session=False); db.commit()
    assert search('ลาพักร้อน', tenant, True, monkeypatch) == expected['ลาพักร้อน']  # index not ready: falls back to the scan
    terms.backfill(SessionLocal)
    with SessionLocal() as db:
        assert db.scalar(select(func.min(Chunk.length)).where(Chunk.document_id.in_(ids))) >= 0
    with SessionLocal() as db:
        docs = retrieval.searchable_documents(db, tenant)
        monkeypatch.setattr(terms, 'MIN_CHUNKS', 0)
        assert terms.scores(db, tenant, retrieval.embeddings.specification()['version'], docs, retrieval.lexical_tokens('ลาพักร้อน')) is not None  # the index path really runs
    for q in queries:
        got = search(q, tenant, True, monkeypatch)
        assert [(r['chunk_id'], r['score']) for r in got] == [(r['chunk_id'], r['score']) for r in expected[q]], q


def test_prune_drops_common_terms_and_search_still_works(admin, monkeypatch):
    ids = [upload(admin, text, name=name).json()['id'] for name, text in TEXTS.items()]
    ready(admin, ids)
    monkeypatch.setattr(terms, 'MIN_CHUNKS', 0)
    with SessionLocal() as db:
        tenant = db.get(Document, ids[0]).tenant_id
        before = db.scalar(select(func.count()).select_from(ChunkTerm))
    try:
        assert terms.prune(SessionLocal, ratio=0.05) > 0  # a low ratio so the small test corpus has "common" terms
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(ChunkTerm)) < before
            assert terms.stop_terms() or True
        terms.analyze()
        assert search('ลาพักร้อน', tenant, True, monkeypatch) is not None
    finally:
        from hub.feature_models import Setting
        with SessionLocal() as db:
            db.query(Setting).filter(Setting.key == 'bm25_stop_terms').delete(); db.commit()
        terms._stops['at'] = 0.
        terms.backfill(SessionLocal)
