FROM python:3.12.12-slim AS builder
WORKDIR /build
COPY apps/api/requirements.lock.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.lock.txt
FROM python:3.12.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data PADDLE_PDX_CACHE_HOME=/data/paddlex PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client-17 libgl1 libglib2.0-0 libgomp1 fonts-dejavu-core antiword && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 10001 app && useradd -u 10001 -g app -m app && mkdir /data /backups && chown app:app /data /backups
COPY --from=builder /wheels /wheels
COPY apps/api/requirements.lock.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r /tmp/requirements.txt && rm -r /wheels
WORKDIR /srv
COPY --chown=app:app apps/api/ ./
USER app
EXPOSE 8000
CMD ["sh","-ec","python -m hub.bootstrap && alembic upgrade head && python -m hub.rls && exec uvicorn hub.main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 75"]
