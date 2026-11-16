from hub import embeddings, onnx_rerank


def test_local_reranker_sorts_by_score(monkeypatch):
    monkeypatch.setenv('RERANK_MODEL', embeddings.LOCAL_RERANKER)
    monkeypatch.delenv('RERANK_MIN_SCORE', raising=False)
    seen = {}
    monkeypatch.setattr(onnx_rerank, 'score', lambda q, ps: seen.update(q=q, ps=ps) or [0.2, 0.9, 0.5])
    out = embeddings.rerank('คำถาม', [{'id': 'a', 'snippet': 'A'}, {'id': 'b', 'snippet': 'B'}, {'id': 'c', 'snippet': 'C'}])
    assert [r['id'] for r in out] == ['b', 'c', 'a']
    assert out[0]['rerank_score'] == 0.9 and seen == {'q': 'คำถาม', 'ps': ['A', 'B', 'C']}


def test_local_reranker_min_score_filters(monkeypatch):
    monkeypatch.setenv('RERANK_MODEL', embeddings.LOCAL_RERANKER)
    monkeypatch.setenv('RERANK_MIN_SCORE', '0.4')
    monkeypatch.setattr(onnx_rerank, 'score', lambda q, ps: [0.2, 0.9])
    out = embeddings.rerank('q', [{'id': 'a', 'snippet': 'A'}, {'id': 'b', 'snippet': 'B'}])
    assert [r['id'] for r in out] == ['b']
