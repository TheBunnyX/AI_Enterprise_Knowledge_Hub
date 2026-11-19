"""Questions without Thai letters keep more candidates for the reranker (the dense cut-off drops Thai passages for an English question)."""
from hub import retrieval


def test_only_a_question_without_thai_letters_is_cross_language(monkeypatch):
    monkeypatch.setenv('RERANK_MODEL', 'local:bge-reranker-v2-m3')
    assert retrieval.cross_language('How many vacation days do I get?')
    assert not retrieval.cross_language('ลาพักร้อนกี่วัน')
    assert not retrieval.cross_language('How many วันลา do I get')  # one Thai word means a Thai-aware query
    assert not retrieval.cross_language('5+5')  # digits and symbols only: not a language, keep the strict floor


def test_it_needs_a_reranker_and_can_be_switched_off(monkeypatch):
    monkeypatch.setenv('RERANK_MODEL', '')
    assert not retrieval.cross_language('vacation days')  # without a reranker nothing would reject weak matches
    monkeypatch.setenv('RERANK_MODEL', 'local:bge-reranker-v2-m3')
    monkeypatch.setenv('CROSS_LANGUAGE_SEARCH', 'false')
    assert not retrieval.cross_language('vacation days')
