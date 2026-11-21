"""BM25 term index in PostgreSQL.

Searching used to read every permitted chunk into memory and tokenise it for each question. The index keeps, per chunk,
its token count (`document_chunks.length`) and how often each token occurs (`chunk_terms`), so a question only touches the
chunks that contain one of its words. Scores are the same BM25 numbers the in-memory path produced.

`python -m hub.terms` builds the index for chunks that have none yet (run at every start; safe to repeat and to interrupt).
"""
import os
from collections import Counter
from sqlalchemy import select, func, insert, update, delete

MIN_CHUNKS = int(os.getenv('SPARSE_INDEX_MIN_CHUNKS', '5000'))  # below this many chunks scanning in memory is as fast; 0 = always use the index
BATCH = 200
STOP_RATIO = float(os.getenv('TERM_STOP_RATIO', '0.5'))  # terms found in more than this share of a big corpus's chunks carry almost no BM25 weight and are dropped from the index; 0 = keep all
_stops = {'at': 0., 'terms': frozenset()}

def stop_terms():
    """Terms pruned from the index (stored in settings by `prune`); cached for a minute."""
    import time
    if time.monotonic() - _stops['at'] < 60: return _stops['terms']
    try:
        from .database import SessionLocal
        from .feature_models import Setting
        with SessionLocal() as db:
            row = db.scalar(select(Setting).where(Setting.key == 'bm25_stop_terms'))
            _stops.update(at=time.monotonic(), terms=frozenset((row.value or {}).get('terms', [])) if row else frozenset())
    except Exception: pass
    return _stops['terms']

def counts(text, name):
    """(token count, {token: occurrences}) of a chunk, the same text BM25 has always scored: the passage plus its document's name."""
    from .retrieval import lexical_tokens
    found = lexical_tokens(text + ' ' + name)
    return len(found), Counter(found)

def build(db, chunks, name):
    """Write the term rows of new Chunk objects (already flushed, so they have ids)."""
    rows = []; stops = stop_terms()
    for c in chunks:
        length, tf = counts(c.text, name)
        c.length = length
        rows += [{'chunk_id': c.id, 'term': t, 'tenant_id': c.tenant_id, 'document_id': c.document_id, 'tf': n} for t, n in tf.items() if t not in stops]
    if rows:
        for i in range(0, len(rows), 5000): db.execute(insert(ChunkTerm), rows[i:i + 5000])

def backfill(session_factory=None, limit=None):
    """Index chunks created before the term index existed. Returns how many chunks were done."""
    if session_factory is None:
        from sqlalchemy.orm import sessionmaker
        from .database import owner_engine
        session_factory = sessionmaker(owner_engine())
    from .models import Chunk, Document
    done = 0
    while True:
        with session_factory() as db:
            rows = db.execute(select(Chunk.id, Chunk.tenant_id, Chunk.document_id, Chunk.text, Document.name).join(Document, Document.id == Chunk.document_id).where(Chunk.length < 0).limit(BATCH)).all()
            if not rows: return done
            terms = []
            for r in rows:
                length, tf = counts(r.text, r.name)
                db.execute(update(Chunk).where(Chunk.id == r.id).values(length=length))
                db.execute(delete(ChunkTerm).where(ChunkTerm.chunk_id == r.id))
                terms += [{'chunk_id': r.id, 'term': t, 'tenant_id': r.tenant_id, 'document_id': r.document_id, 'tf': n} for t, n in tf.items()]
            if terms:
                for i in range(0, len(terms), 5000): db.execute(insert(ChunkTerm), terms[i:i + 5000])
            db.commit(); done += len(rows)
        if limit and done >= limit: return done

def scores(db, tenant_id, version, docs, terms):
    """BM25 from the index: (sparse [(score, chunk_id)], chunk count in scope), or None when the index is not ready or not worth using.

    `docs` are the documents the user may read; the statistics (chunk count, average length, document frequency) are taken over
    exactly those, as the in-memory scan does."""
    from .models import Chunk
    import math
    stats = db.execute(select(Chunk.document_id, func.count(), func.sum(Chunk.length), func.min(Chunk.length)).where(Chunk.tenant_id == tenant_id, Chunk.embedding_version == version).group_by(Chunk.document_id)).all()
    mine = [r for r in stats if r[0] in docs]
    count = sum(r[1] for r in mine)
    if count < MIN_CHUNKS or any(r[3] < 0 for r in mine): return None
    average = (sum(r[2] for r in mine) / count) or 1
    if not terms: return [], count
    stops = stop_terms()
    wanted = [t for t in terms if t not in stops]  # pruned terms are not indexed any more (their weight is almost zero)
    if not wanted: return [], count
    frequency = Counter()
    for document_id, term, n in db.execute(select(ChunkTerm.document_id, ChunkTerm.term, func.count()).where(ChunkTerm.tenant_id == tenant_id, ChunkTerm.term.in_(wanted)).group_by(ChunkTerm.document_id, ChunkTerm.term)):
        if document_id in docs: frequency[term] += n
    tf = {}
    for chunk_id, document_id, term, n in db.execute(select(ChunkTerm.chunk_id, ChunkTerm.document_id, ChunkTerm.term, ChunkTerm.tf).where(ChunkTerm.tenant_id == tenant_id, ChunkTerm.term.in_(wanted))):
        if document_id in docs: tf.setdefault(chunk_id, {})[term] = n
    if not tf: return [], count
    lengths = {}
    ids = list(tf)
    for i in range(0, len(ids), 5000):
        lengths.update({r[0]: r[1] for r in db.execute(select(Chunk.id, Chunk.length).where(Chunk.id.in_(ids[i:i + 5000]), Chunk.embedding_version == version))})
    out = []
    for chunk_id, row in tf.items():
        if chunk_id not in lengths: continue
        length = lengths[chunk_id]; score = 0.
        for t in wanted:
            n = row.get(t)
            if n: score += math.log(1 + (count - frequency[t] + .5) / (frequency[t] + .5)) * (n * 2.2) / (n + 1.2 * (.25 + .75 * length / average))
        out.append((score, chunk_id))
    return out, count

def prune(session_factory=None, ratio=None):
    """Drop terms that occur in more than `ratio` of all chunks (and remember them) once the corpus is big. Returns how many terms went."""
    from .models import Chunk
    from .feature_models import Setting
    ratio = STOP_RATIO if ratio is None else ratio
    if ratio <= 0: return 0
    if session_factory is None:
        from sqlalchemy.orm import sessionmaker
        from .database import owner_engine
        session_factory = sessionmaker(owner_engine())
    with session_factory() as db:
        total = db.scalar(select(func.count()).select_from(Chunk))
        if not total or total < MIN_CHUNKS: return 0
        common = [r[0] for r in db.execute(select(ChunkTerm.term).group_by(ChunkTerm.term).having(func.count() > ratio * total))]
        if not common: return 0
        row = db.scalar(select(Setting).where(Setting.key == 'bm25_stop_terms'))
        if not row: row = Setting(key='bm25_stop_terms'); db.add(row)
        row.value = {'terms': sorted(set(common) | set((row.value or {}).get('terms', [])))}
        for i in range(0, len(common), 500): db.execute(delete(ChunkTerm).where(ChunkTerm.term.in_(common[i:i + 500])))
        db.commit()
    _stops['at'] = 0.
    return len(common)

def analyze():
    """Refresh planner statistics and reclaim space after a bulk load (outside a transaction)."""
    from .database import owner_engine
    with owner_engine().connect().execution_options(isolation_level='AUTOCOMMIT') as c:
        c.exec_driver_sql('VACUUM (ANALYZE) chunk_terms'); c.exec_driver_sql('VACUUM (ANALYZE) document_chunks')

from .models import ChunkTerm  # noqa: E402  (after the functions so retrieval can import this module lazily)

if __name__ == '__main__':
    done = backfill()
    gone = prune()
    if done or gone: analyze()
    print('terms: indexed', done, 'chunks; pruned', gone, 'common terms')
