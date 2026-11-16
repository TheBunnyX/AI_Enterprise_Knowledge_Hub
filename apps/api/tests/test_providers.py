from conftest import login_as
from cryptography.fernet import Fernet
from sqlalchemy import select
from hub import gateway
from hub.database import SessionLocal
from hub.feature_models import Setting


def test_provider_keys_are_per_provider_and_encrypted(admin, monkeypatch):
    monkeypatch.delenv('GOOGLE_AI_API_KEY', raising=False)
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.setenv('SECRETS_KEY', Fernet.generate_key().decode())
    assert admin.put('/api/admin/gateway', json={'url': 'https://default.test/v1', 'api_key': 'default-key'}).status_code == 200
    assert admin.put('/api/admin/providers/Google AI', json={'api_key': 'google-secret'}).status_code == 200
    assert admin.put('/api/admin/providers/OpenRouter', json={'api_key': 'router-secret'}).status_code == 200
    assert admin.put('/api/admin/providers/Custom', json={'api_key': 'x'}).status_code == 422  # unknown provider needs a URL

    listing = {p['name']: p for p in admin.get('/api/admin/providers').json()}
    assert listing['Google AI']['key_configured'] and listing['Google AI']['url'].startswith('https://generativelanguage.googleapis.com')
    assert listing['OpenRouter']['url'] == 'https://openrouter.ai/api/v1'
    assert 'google-secret' not in str(listing) and 'router-secret' not in str(listing)

    with SessionLocal() as db:
        assert 'google-secret' not in str(db.scalar(select(Setting).where(Setting.key == 'providers')).value)
        assert gateway.configuration(db, 'Google AI')[1] == 'google-secret'
        assert gateway.configuration(db, 'OpenRouter') == ('https://openrouter.ai/api/v1', 'router-secret')
        assert gateway.configuration(db, 'Unknown') == ('https://default.test/v1', 'default-key')  # falls back to the default gateway
        assert gateway.configuration(db) == ('https://default.test/v1', 'default-key')

    assert admin.delete('/api/admin/providers/OpenRouter').status_code == 200
    with SessionLocal() as db:
        assert gateway.configuration(db, 'OpenRouter')[1] == 'default-key'

    login_as(admin,'member')
    assert admin.get('/api/admin/providers').status_code == 403


def test_provider_key_from_env_wins_and_is_read_only(admin, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'env-router-key')
    with SessionLocal() as db:
        assert gateway.configuration(db, 'OpenRouter') == ('https://openrouter.ai/api/v1', 'env-router-key')
        assert gateway.configured(db, 'OpenRouter')
    listing = {p['name']: p for p in admin.get('/api/admin/providers').json()}
    assert listing['OpenRouter']['key_configured'] and listing['OpenRouter']['source'] == 'env'
    assert 'env-router-key' not in str(listing)
    assert admin.put('/api/admin/providers/OpenRouter', json={'api_key': 'x'}).status_code == 409  # edit .env instead


def test_local_llm_provider_needs_no_key(monkeypatch):
    monkeypatch.setenv('LOCAL_LLM_URL', 'http://llm.test:8080/v1/')
    with SessionLocal() as db:
        assert gateway.configuration(db, 'Local LLM') == ('http://llm.test:8080/v1', '')
        assert gateway.configured(db, 'Local LLM')
