import httpx
from hub import decisions, cite_check


class Reply:
    def __init__(self, data, status=200): self.data, self.status_code = data, status
    def json(self): return self.data
    def raise_for_status(self):
        if self.status_code >= 400: raise httpx.HTTPStatusError('x', request=None, response=None)


def on(monkeypatch, reply):
    monkeypatch.setenv('DECISIONS_ENABLED', 'true')
    monkeypatch.setattr(decisions, '_key', lambda: 'k')
    decisions._failed_at[0] = 0.0
    sent = []
    def post(url, **kw):
        sent.append(kw['json'])
        if isinstance(reply, Exception): raise reply
        return reply
    monkeypatch.setattr(decisions.httpx, 'post', post)
    return sent


def test_off_by_default(monkeypatch):
    monkeypatch.delenv('DECISIONS_ENABLED', raising=False)
    assert decisions.relevant('q', ['p']) is None and decisions.support(['claim'], ['p']) is None


def test_relevance_probability(monkeypatch):
    sent = on(monkeypatch, Reply({'answers': {'answers_it': {'type': 'noul', 'noul': 0.07, 'confidence': 0.93}}}))
    assert decisions.relevant('5+5', ['x']) == 0.07
    assert sent[0]['model'] == 'gemini-decision-1' and sent[0]['questions']['answers_it']['type'] == 'noul'


def test_failure_falls_back_and_backs_off(monkeypatch):
    sent = on(monkeypatch, httpx.ConnectError('down'))
    assert decisions.relevant('q', ['p']) is None
    assert decisions.relevant('q', ['p']) is None and len(sent) == 1  # second call does not even try
    assert not decisions.enabled()


def test_blocked_input_is_not_an_outage(monkeypatch):
    on(monkeypatch, Reply({'error': {'code': 'safety', 'message': 'x'}}, 400))
    assert decisions.relevant('q', ['p']) is None and decisions.enabled()


def test_support_maps_choices_to_passages(monkeypatch):
    on(monkeypatch, Reply({'answers': {
        'c0': {'type': 'choice', 'choice': 'p002', 'probabilities': {'p001': 0.1, 'p002': 0.8, 'none': 0.1}},
        'c1': {'type': 'choice', 'choice': 'none', 'probabilities': {'p001': 0.2, 'p002': 0.1, 'none': 0.7}}}}))
    assert decisions.support(['a', 'b'], ['one', 'two']) == [[2], []]


def test_verify_uses_the_judge_and_falls_back():
    answer = 'ลาพักร้อนได้สิบวันต่อปี [1] พนักงานใหม่ต้องรอหกเดือนก่อนลา [2]'
    passages = ['ลาพักร้อนได้สิบวันต่อปี', 'พนักงานใหม่ต้องรอหกเดือนก่อนลา']
    swapped = cite_check.verify(answer, passages, judge=lambda claims: [[2], []])
    assert '[2]' in swapped.split('พนักงาน')[0] and swapped.rstrip().endswith('ก่อนลา')  # first marker re-pointed, second dropped
    assert cite_check.verify(answer, passages, judge=lambda claims: None) == cite_check.verify(answer, passages)


def test_openrouter_models_use_their_own_dialect(monkeypatch):
    for name in ('typesafe/jev-1.13', 'typesafe/jev-1.14', 'perplexity/pplx-decider-v1.2'):
        monkeypatch.setenv('DECISIONS_MODEL', name)
        sent = on(monkeypatch, Reply({'answers': {'answers_it': {'type': 'noul', 'noul': 0.9}}}))
        urls = []
        monkeypatch.setattr(decisions.httpx, 'post', lambda url, **kw: (urls.append((url, kw)), Reply({'answers': {'answers_it': {'type': 'noul', 'noul': 0.9}}}))[1])
        assert decisions.relevant('q', ['p']) == 0.9
        url, kw = urls[0]
        assert url == decisions.OPENROUTER_URL and kw['headers']['Authorization'] == 'Bearer k'
        assert kw['json']['model'] == name and kw['json']['state'].startswith('Question:') and 'input' not in kw['json']
        assert set(kw['json']['questions']['answers_it']['criteria']) == {'true', 'false'}


def test_google_model_keeps_google_dialect(monkeypatch):
    monkeypatch.delenv('DECISIONS_MODEL', raising=False)
    sent = on(monkeypatch, Reply({'answers': {'answers_it': {'type': 'noul', 'noul': 0.5}}}))
    decisions.relevant('q', ['p'])
    assert 'input' in sent[0] and 'state' not in sent[0] and 'true_description' in sent[0]['questions']['answers_it']['criteria']


def test_refusal_falls_back(monkeypatch):
    on(monkeypatch, Reply({'answers': {'answers_it': {'type': 'refusal'}}}))
    assert decisions.relevant('q', ['p']) is None and decisions.enabled()
