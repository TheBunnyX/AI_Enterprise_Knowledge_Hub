"""Retrieval evaluation: does search put the passage that answers a question at the top?

Indexes eval/corpus through the real pipeline (parse -> split -> embed) into a throwaway PostgreSQL database (Compose, see compose.dev.yaml), runs every
question in eval/questions.jsonl through retrieval.search and reports, per search mode:

  hit@1   the top result contains the answer
  hit@k   one of the top k results contains the answer (k = what chat sends to the model, default 4)
  MRR     mean of 1/rank of the first result that contains the answer
  doc@k   one of the top k results comes from the right document (answer phrase or not)

A result "contains the answer" when it comes from the expected document and includes the expected phrase, so the
scores stay comparable when chunk boundaries change. No LLM is called and nothing leaves the machine.

    python -m eval.run                        # embedding model from the environment / .env
    python -m eval.run --embedding hash       # the built-in hash baseline (no model download)
    python -m eval.run --json result.json --min-hit 0.85   # for CI: fail when hybrid hit@k drops below the bar
"""
import argparse, json, os, re, shutil, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = HERE.parent


def squash(text): return re.sub(r'\s+', '', text)


def load_questions():
    questions = [json.loads(line) for line in (HERE / 'questions.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    for item in questions:  # a gold phrase that is not in its document would silently score zero
        text = squash((HERE / 'corpus' / item['doc']).read_text(encoding='utf-8'))
        if squash(item['answer']) not in text: raise SystemExit(f"answer not found in {item['doc']}: {item['answer']}")
    return questions


DROP = [lambda: None]


def configure(embedding):
    """Point the app at a throwaway database before it is imported. Model files stay cached in data/eval between runs."""
    env_file = API.parent.parent / '.env'
    if embedding is None and env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            if line.startswith(('EMBEDDING_', 'OCR_')) and '=' in line:
                key, value = line.split('=', 1); os.environ.setdefault(key, value.strip())
    elif embedding is not None:
        os.environ['EMBEDDING_MODEL'] = '' if embedding == 'hash' else embedding
    data = API / 'data' / 'eval'; data.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='run-', dir=data))
    os.environ['DATA_DIR'] = str(data)
    sys.path.insert(0, str(API))
    from hub.scratch_db import create
    os.environ['DATABASE_URL'], DROP[0] = create('hub_eval')  # throw-away database on the Compose PostgreSQL
    os.environ.pop('MIGRATION_DATABASE_URL', None)
    for key in ('S3_ENDPOINT', 'QDRANT_URL', 'CELERY_BROKER_URL', 'CLAMAV_HOST', 'RERANK_MODEL', 'APP_ENV'): os.environ.pop(key, None)
    sys.path.insert(0, str(API))
    return work


def build_index():
    from hub.database import Base, SessionLocal, engine
    from hub import models, feature_models, ops_models, savings_models, storage, retrieval  # noqa: F401 - registers the tables
    from hub.models import Organization, KnowledgeBase, Document, Chunk
    from sqlalchemy import select, func
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        org = Organization(name='eval'); db.add(org); db.flush()
        kb = KnowledgeBase(tenant_id=org.id, name='eval'); db.add(kb); db.flush()
        ids = []
        for path in sorted((HERE / 'corpus').glob('*.md')):
            raw = path.read_bytes(); key = f'{org.id}/eval/{path.name}'; storage.put(key, raw)
            d = Document(tenant_id=org.id, knowledge_base_id=kb.id, name=path.name, sha256=path.name, size=len(raw), storage_key=key)
            db.add(d); db.flush(); ids.append(d.id)
        db.commit(); tenant = org.id
    for id in ids: retrieval.ingest(id, raise_errors=True)
    with SessionLocal() as db:
        count, chars = db.execute(select(func.count(), func.avg(func.length(Chunk.text)))).one()
    return tenant, {'documents': len(ids), 'chunks': count, 'average_chunk_chars': round(chars or 0)}


def evaluate(tenant, questions, modes, k):
    from hub.database import SessionLocal
    from hub import retrieval
    report = {}; misses = {}
    for mode in modes:
        first = []; right_doc = 0
        with SessionLocal() as db:
            for item in questions:
                found = retrieval.search(db, tenant, item['q'], mode=mode, limit=k)
                rank = next((i + 1 for i, r in enumerate(found) if r['name'] == item['doc'] and squash(item['answer']) in squash(r['snippet'])), 0)
                first.append(rank); right_doc += any(r['name'] == item['doc'] for r in found)
                if not rank: misses.setdefault(mode, []).append(item['q'])
        n = len(questions)
        report[mode] = {'hit@1': round(sum(r == 1 for r in first) / n, 3), f'hit@{k}': round(sum(r > 0 for r in first) / n, 3),
                        'mrr': round(sum(1 / r for r in first if r) / n, 3), f'doc@{k}': round(right_doc / n, 3)}
    return report, misses


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--embedding', help='embedding model; "hash" for the built-in baseline; default: EMBEDDING_MODEL from .env')
    parser.add_argument('--modes', default='hybrid,keyword,semantic')
    parser.add_argument('-k', type=int, default=4)
    parser.add_argument('--json', help='write the full report to this file')
    parser.add_argument('--min-hit', type=float, default=0, help='exit 1 when hybrid hit@k is below this (for CI)')
    parser.add_argument('--misses', action='store_true', help='list the questions each mode failed')
    args = parser.parse_args()
    questions = load_questions(); work = configure(args.embedding)
    try:
        tenant, index = build_index()
        report, misses = evaluate(tenant, questions, args.modes.split(','), args.k)
    finally:
        from hub.database import engine
        engine.dispose(); DROP[0](); shutil.rmtree(work, ignore_errors=True)
    from hub import embeddings
    out = {'embedding': embeddings.specification()['model'] or 'hash-ngram baseline', 'questions': len(questions), 'k': args.k, **index, 'modes': report}
    print(f"embedding: {out['embedding']} | {index['documents']} documents, {index['chunks']} chunks (avg {index['average_chunk_chars']} chars) | {len(questions)} questions")
    columns = list(next(iter(report.values())))
    print(f"{'mode':<10}" + ''.join(f'{c:>9}' for c in columns))
    for mode, row in report.items(): print(f'{mode:<10}' + ''.join(f'{row[c]:>9.3f}' for c in columns))
    if args.misses:
        for mode, items in misses.items():
            print(f'\n{mode} missed {len(items)}:'); [print('  -', q) for q in items]
    if args.json: Path(args.json).write_text(json.dumps(out | {'misses': misses}, ensure_ascii=False, indent=1), encoding='utf-8')
    hybrid = report.get('hybrid', {}).get(f'hit@{args.k}')
    if args.min_hit and hybrid is not None and hybrid < args.min_hit:
        print(f'FAIL: hybrid hit@{args.k} {hybrid} is below {args.min_hit}'); sys.exit(1)


if __name__ == '__main__':
    main()
