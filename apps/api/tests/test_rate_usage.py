from datetime import datetime, timedelta, timezone
from hub.database import SessionLocal
from hub.models import Usage
from hub.routes import rate_usage


def test_counts_per_provider_minute_and_day(admin):
    now = datetime.now(timezone.utc)
    def add(db, provider, age_s, tokens, model='Gemini 3.5 Flash Lite'):
        db.add(Usage(tenant_id='t', user_id='u', model=model, provider=provider, input_tokens=tokens, output_tokens=0, created_at=(now - timedelta(seconds=age_s)).isoformat()))
    with SessionLocal() as db:
        add(db, 'Google AI', 5, 100)        # inside the last minute
        add(db, 'Google AI', 20, 50)        # inside the last minute
        add(db, 'Google AI', 600, 70)       # earlier, only counts toward the day (unless just past midnight Pacific)
        add(db, 'OpenRouter', 5, 999)       # same model name, other provider: counted separately
        db.commit()
    out = rate_usage()
    rpm, tpm, rpd = out[('Google AI', 'Gemini 3.5 Flash Lite')]
    assert (rpm, tpm) == (2, 150) and rpd >= 2
    assert out[('OpenRouter', 'Gemini 3.5 Flash Lite')][:2] == (1, 999)
