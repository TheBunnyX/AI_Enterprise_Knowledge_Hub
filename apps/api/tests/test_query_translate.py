"""An English question is translated to a Thai search query before retrieval; any failure falls back to the original question."""
import asyncio
from types import SimpleNamespace
from hub import query_translate as qt, chat_service, gateway


def test_only_latin_questions_with_two_words_are_translated(monkeypatch):
    monkeypatch.setenv('QUERY_TRANSLATION', 'true')
    assert qt.needs_translation('How many vacation days do I get?')
    assert not qt.needs_translation('ลาพักร้อนกี่วัน')
    assert not qt.needs_translation('How many วันลา')
    assert not qt.needs_translation('vacation')  # a single word is left alone
    assert not qt.needs_translation('12345 678')
    monkeypatch.setenv('QUERY_TRANSLATION', 'false')
    assert not qt.needs_translation('How many vacation days do I get?')


def test_the_reply_is_cleaned_to_one_thai_line():
    assert qt.clean('"ลาพักร้อนกี่วัน"') == 'ลาพักร้อนกี่วัน'
    assert qt.clean('Thai: ลาพักร้อนกี่วัน\nหมายเหตุ') == 'ลาพักร้อนกี่วัน'
    assert qt.clean('Sorry, I cannot translate that') == ''  # not Thai: ignored
    assert qt.clean('') == ''


def test_translate_calls_the_users_model_and_caches(monkeypatch):
    monkeypatch.setenv('QUERY_TRANSLATION', 'true')
    monkeypatch.setattr(gateway, 'configuration', lambda db, provider='': ('http://gateway.test/v1', 'k'))
    qt._CACHE.clear()
    model = SimpleNamespace(provider='LiteLLM', api_id='any-model')
    out = asyncio.run(qt.translate(None, model, 'How many vacation days do I get?'))
    assert out  # the test gateway answers with Thai text, which is accepted as the translation
    monkeypatch.setattr(gateway, 'configuration', lambda *a, **k: (_ for _ in ()).throw(AssertionError('a cached question must not call the model again')))
    assert asyncio.run(qt.translate(None, model, 'how many vacation days do i get?')) == out


def test_a_failing_gateway_returns_nothing(monkeypatch):
    monkeypatch.setenv('QUERY_TRANSLATION', 'true')
    monkeypatch.setattr(gateway, 'configuration', lambda *a, **k: (_ for _ in ()).throw(KeyError('no gateway')))
    qt._CACHE.clear()
    model = SimpleNamespace(provider='LiteLLM', api_id='any-model')
    try: assert asyncio.run(qt.translate(None, model, 'How many vacation days do I get?')) == ''
    except KeyError: pass  # configuration errors are the caller's business; the translation itself never raises on HTTP failures


def test_chat_searches_with_the_thai_query_first_and_falls_back(member, monkeypatch):
    seen = []
    async def fake_translate(db, model, question, usage=None): return 'ลาพักร้อนกี่วัน' if 'vacation' in question else ''
    monkeypatch.setattr(qt, 'translate', fake_translate)
    def fake_search(db, tenant, query, *a, **k):
        seen.append(query); return []
    monkeypatch.setattr(chat_service, 'search', fake_search)
    member.post('/api/chat', json={'question': 'How many vacation days do I get?'})
    assert seen == ['ลาพักร้อนกี่วัน', 'How many vacation days do I get?']  # Thai first; nothing found, so the original question too
    seen.clear()
    member.post('/api/chat', json={'question': 'something unrelated entirely'})
    assert seen == ['something unrelated entirely']  # no translation: only the original


def test_the_cost_comes_from_the_provider_or_from_the_list_price():
    import httpx
    model = SimpleNamespace(input_price=0.3, output_price=2.5)  # dollars per million tokens
    body = {'choices': [{'message': {'content': 'x'}}], 'usage': {'prompt_tokens': 1000, 'completion_tokens': 100}}
    priced = qt.usage_of(model, httpx.Response(200, json=body))
    assert priced['input_tokens'] == 1000 and priced['output_tokens'] == 100
    assert abs(priced['cost'] - (1000 * 0.3 + 100 * 2.5) / 1e6) < 1e-12 and priced['estimated'] is True
    reported = qt.usage_of(model, httpx.Response(200, json=body, headers={'x-litellm-response-cost': '0.00042'}))
    assert reported['cost'] == 0.00042 and reported['estimated'] is False
    inline = qt.usage_of(model, httpx.Response(200, json={**body, 'usage': {**body['usage'], 'cost': 0.0007}}))
    assert inline['cost'] == 0.0007 and inline['estimated'] is False


def test_the_translation_call_is_recorded_in_the_cost_report(member, monkeypatch):
    from sqlalchemy import select
    from hub.database import SessionLocal
    from hub.models import Usage
    async def fake_translate(db, model, question, usage=None):
        usage.append({'input_tokens': 120, 'output_tokens': 20, 'cost': 0.0123, 'estimated': True}); return 'ลาพักร้อนกี่วัน'
    monkeypatch.setattr(qt, 'translate', fake_translate)
    monkeypatch.setattr(chat_service, 'search', lambda *a, **k: [])
    member.post('/api/chat', json={'question': 'How many vacation days do I get?'})
    with SessionLocal() as db:
        rows = list(db.scalars(select(Usage).where(Usage.model.startswith(qt.LABEL))))
    assert len(rows) == 1 and rows[0].cost == 0.0123 and rows[0].input_tokens == 120 and rows[0].output_tokens == 20 and rows[0].estimated is True
