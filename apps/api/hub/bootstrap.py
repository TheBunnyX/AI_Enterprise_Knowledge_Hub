import os, time
from .database import owner_engine
engine=owner_engine()
from sqlalchemy import text
for attempt in range(60):
    try:
        with engine.connect() as conn: conn.execute(text('SELECT 1'))
        break
    except Exception:
        if attempt==59: raise
        time.sleep(2)
if os.getenv('S3_ENDPOINT'):
    from .storage import s3
    bucket=os.getenv('S3_BUCKET','knowledge')
    for attempt in range(60):
        try:
            client=s3()
            try: client.head_bucket(Bucket=bucket)
            except Exception: client.create_bucket(Bucket=bucket)
            break
        except Exception:
            if attempt==59: raise
            time.sleep(2)
if os.getenv('QDRANT_URL'):
    import httpx
    for attempt in range(60):
        try:
            response=httpx.get(os.environ['QDRANT_URL'].rstrip('/')+'/readyz',timeout=5)
            response.raise_for_status();break
        except httpx.HTTPError:
            if attempt==59: raise
            time.sleep(2)
