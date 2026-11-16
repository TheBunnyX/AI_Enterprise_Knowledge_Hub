"""Trusted gateway settings. API keys are encrypted at rest and never serialized."""
import os,re
from urllib.parse import urlparse
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select
from .database import SessionLocal
from .feature_models import Setting

def cipher():
    key=os.getenv('SECRETS_KEY')
    if not key:raise HTTPException(503,'ต้องตั้งค่า SECRETS_KEY ก่อนบันทึก API key')
    return Fernet(key.encode())

# OpenAI-compatible endpoints known by provider name; the admin only supplies the API key.
KNOWN_PROVIDERS={'Google AI':'https://generativelanguage.googleapis.com/v1beta/openai','OpenRouter':'https://openrouter.ai/api/v1'}

# Providers that need no API key (self-hosted, on the compose network).
KEYLESS_PROVIDERS={'Local LLM':lambda:os.getenv('LOCAL_LLM_URL','http://llm-local:8080/v1')}

def env_key(provider):
    """API key kept in .env as <PROVIDER>_API_KEY (Google AI -> GOOGLE_AI_API_KEY); wins over a key saved in the database."""
    return os.getenv(re.sub(r'[^A-Z0-9]+','_',provider.upper()).strip('_')+'_API_KEY','').strip() if provider else ''

def provider_settings(db):
    s=db.scalar(select(Setting).where(Setting.key=='providers'))
    return dict(s.value) if s else {}

def configuration(db=None,provider=''):
    """(url, key) for a provider that has its own entry, otherwise the default gateway."""
    if db is None:
        with SessionLocal() as session:return configuration(session,provider)
    if provider in KEYLESS_PROVIDERS:return KEYLESS_PROVIDERS[provider]().rstrip('/'),''
    if provider and env_key(provider):
        own=provider_settings(db).get(provider) or {}
        return (own.get('url') or KNOWN_PROVIDERS.get(provider) or os.getenv('LITELLM_URL','')).rstrip('/'),env_key(provider)
    if provider:
        own=provider_settings(db).get(provider)
        if own and own.get('encrypted_key'):
            return (own.get('url') or KNOWN_PROVIDERS.get(provider,'')).rstrip('/'),cipher().decrypt(own['encrypted_key'].encode()).decode()
    s=db.scalar(select(Setting).where(Setting.key=='gateway'))
    value=s.value if s else {}
    url=value.get('url') or os.getenv('LITELLM_URL','')
    key=cipher().decrypt(value['encrypted_key'].encode()).decode() if value.get('encrypted_key') else os.getenv('LITELLM_KEY','')
    return url.rstrip('/'),key

def configured(db=None,provider=''):
    """Usable: has a URL, and a key when the provider is a hosted one (Google AI, OpenRouter) that cannot work without it."""
    url,key=configuration(db,provider)
    return bool(url) and (bool(key) or provider not in KNOWN_PROVIDERS)
def headers(key):return {'Authorization':'Bearer '+key,'x-litellm-api-key':key} if key else {}  # keyless providers (Local LLM): an empty 'Bearer ' is an illegal header value

def validate_url(url):
    parsed=urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(422,'Gateway URL ต้องเป็น HTTP/HTTPS และไม่มีรหัสผ่านหรือ query string')
    if os.getenv('APP_ENV')=='production' and parsed.scheme!='https':
        raise HTTPException(422,'Production Gateway ต้องใช้ HTTPS')


def effort_params(model):
    """Reasoning effort for a chat request. OpenRouter takes reasoning.effort; the OpenAI-compatible gateways take reasoning_effort."""
    effort = model.get('effort') or ''
    if not effort: return {}
    return {'reasoning': {'effort': effort}} if model.get('provider') == 'OpenRouter' else {'reasoning_effort': effort}
