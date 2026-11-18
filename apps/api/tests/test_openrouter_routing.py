"""OpenRouter routing: cheapest provider first by default, configurable, and never sent to other gateways."""
import json
import httpx
from hub import gateway
from test_platform import upload


def test_routing_defaults_to_the_cheapest_provider_on_openrouter(monkeypatch):
    monkeypatch.delenv('OPENROUTER_SORT', raising=False)
    assert gateway.routing('OpenRouter') == {'provider': {'sort': 'price'}}
    assert gateway.routing('', 'https://openrouter.ai/api/v1') == {'provider': {'sort': 'price'}}  # the default gateway pointing at OpenRouter
    assert gateway.routing('Google AI') == {} and gateway.routing('Local LLM') == {} and gateway.routing('', 'http://litellm:4000') == {}


def test_routing_can_be_changed_or_switched_off(monkeypatch):
    monkeypatch.setenv('OPENROUTER_SORT', 'throughput')
    assert gateway.routing('OpenRouter') == {'provider': {'sort': 'throughput'}}
    monkeypatch.setenv('OPENROUTER_SORT', '')
    assert gateway.routing('OpenRouter') == {}
    monkeypatch.setenv('OPENROUTER_SORT', 'nonsense')
    assert gateway.routing('OpenRouter') == {}


def test_a_chat_through_openrouter_asks_for_the_cheapest_provider(department, monkeypatch):
    from conftest import login_as
    monkeypatch.delenv('OPENROUTER_SORT', raising=False)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
    assert upload(department).status_code == 201
    sent = []
    def respond(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'ตอบ'}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5}})
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda *a, **kw: real(*a, **{**kw, 'transport': httpx.MockTransport(respond)}))
    from sqlalchemy import select
    from hub.database import SessionLocal
    from hub.models import AIModel
    with SessionLocal() as db:
        m = AIModel(name='Test OR', provider='OpenRouter', api_id='deepseek/test', category='LLM', enabled=True); db.add(m); db.commit(); model_id = m.id
    assert department.post('/api/chat', json={'question': 'ลาพักร้อนได้กี่วัน', 'model_id': model_id}).status_code == 200
    assert sent and sent[-1]['provider'] == {'sort': 'price'}
