from hub import embeddings


def test_local_e5_specification_and_routing(monkeypatch):
    monkeypatch.setenv('EMBEDDING_MODEL', embeddings.LOCAL_E5)
    spec = embeddings.specification()
    assert spec['dimensions'] == 384 and spec['version'] == 'onnx-e5-small-v1' and spec['min_score'] == 0.80

    from hub import onnx_embed
    calls = []
    monkeypatch.setattr(onnx_embed, 'embed', lambda texts, kind: calls.append((tuple(texts), kind)) or [[0.0] * 384 for _ in texts])
    embeddings.batch(['เอกสาร'], 't1')
    embeddings.batch(['คำถาม'], 't1', 'query')
    assert calls == [(('เอกสาร',), 'passage'), (('คำถาม',), 'query')]


def test_hash_baseline_unchanged_without_model(monkeypatch):
    monkeypatch.setenv('EMBEDDING_MODEL', '')
    assert embeddings.specification()['version'] == 'hash-ngram-v1-256'
    assert len(embeddings.batch(['x'])[0]) == 256
