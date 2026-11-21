from hub import embeddings


def run(monkeypatch, top, scores):
    monkeypatch.setenv('RERANK_MODEL', embeddings.LOCAL_RERANKER)
    monkeypatch.setenv('RERANK_MIN_SCORE', '0.003')
    monkeypatch.setenv('RERANK_TOP_MIN', top)
    import hub.onnx_rerank as onnx
    monkeypatch.setattr(onnx, 'score', lambda q, texts: scores)
    return embeddings.rerank('q', [{'snippet': 'a'}, {'snippet': 'b'}])


def test_weak_best_passage_gives_no_evidence(monkeypatch):
    assert run(monkeypatch, '0.5', [0.4, 0.01]) == []


def test_strong_best_passage_is_kept(monkeypatch):
    assert len(run(monkeypatch, '0.5', [0.9, 0.01])) == 2


def test_off_by_default(monkeypatch):
    assert len(run(monkeypatch, '0', [0.4, 0.01])) == 2
