#!/usr/bin/env bash
# Adds the Langfuse settings to .env (random secrets, never overwritten if present) so compose.langfuse.yaml can start.
set -euo pipefail
cd "$(dirname "$0")/.."
touch .env
add() { grep -q "^$1=" .env || echo "$1=$2" >> .env; }
rand() { openssl rand -hex "$1"; }
add LANGFUSE_PUBLIC_KEY "pk-lf-$(rand 16)"
add LANGFUSE_SECRET_KEY "sk-lf-$(rand 16)"
add LANGFUSE_HOST "http://langfuse-web:3000"
add LANGFUSE_CAPTURE_CONTENT "true"
add LANGFUSE_DB_PASSWORD "$(rand 16)"
add LANGFUSE_CLICKHOUSE_PASSWORD "$(rand 16)"
add LANGFUSE_REDIS_PASSWORD "$(rand 16)"
add LANGFUSE_SALT "$(rand 16)"
add LANGFUSE_ENCRYPTION_KEY "$(rand 32)"
add LANGFUSE_NEXTAUTH_SECRET "$(rand 16)"
add LANGFUSE_INIT_USER_EMAIL "admin@langfuse.local"
add LANGFUSE_INIT_USER_PASSWORD "$(rand 12)"
# Langfuse keeps raw events in an S3 bucket; the app's SeaweedFS is reused, so create the bucket once.
docker compose exec -T api python - <<'PY' || echo "Start the app first (docker compose up -d), then run this script again to create the bucket."
import os, boto3
s3 = boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT'], aws_access_key_id=os.environ['S3_ACCESS_KEY'], aws_secret_access_key=os.environ['S3_SECRET_KEY'], region_name='us-east-1')
try: s3.create_bucket(Bucket='langfuse')
except Exception as e: print('bucket:', e.__class__.__name__)
print('bucket langfuse ready')
PY
echo "Langfuse settings are in .env. Start it with:"
echo "  docker compose -f compose.yaml -f compose.langfuse.yaml up -d"
echo "Open http://localhost:3100 and sign in with LANGFUSE_INIT_USER_EMAIL / LANGFUSE_INIT_USER_PASSWORD from .env."
