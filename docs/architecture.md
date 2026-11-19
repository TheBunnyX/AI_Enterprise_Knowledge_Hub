# Current architecture changes

See [feature-status.md](feature-status.md) for the current authoritative feature map. Added KB-level reader/writer ACLs, model policies/budgets, document states/versions, encrypted Gateway settings, preferences, feedback and durable media jobs. Chat now streams upstream SSE incrementally with authorized fallback; OCR runs locally in Docker. Learned embedding/reranker adapters are optional, version-separated and require configured Gateway aliases. The original baseline description below is retained for context; statements about missing media adapters or pre-buffered chat have been superseded.

# Architecture

## Runtime

Browser → Next.js server (external port 3009, container port 3000) → same-origin `/api/*` reverse proxy → FastAPI (port 8000 internal / 8100 loopback).

Next.js reads the HttpOnly session cookie on the server and fetches the current user before rendering. FastAPI remains the authorization authority. Hiding navigation alone never grants or denies access.

FastAPI uses SQLAlchemy 2 with PostgreSQL (the Compose database; there is no SQLite mode, so row-level security and migrations behave the same everywhere). Celery receives document UUIDs via Redis; original files live in private SeaweedFS S3 with random tenant-prefixed keys. The bucket is not served publicly. Downloads flow through an authenticated endpoint and are forced as attachments.

## Implemented data entities

Organizations, users (one tenant and role per account), sessions, OIDC authorization state, knowledge bases, documents, document chunks, conversations, messages (citation JSON), AI model registry, usage events and audit logs. UUID IDs, tenant indexes and a tenant + SHA-256 uniqueness constraint. This is an operational subset of the larger requested schema.

## Ingestion

Upload → role/tenant/knowledge-base check → size/type/signature/Office archive-size validation → SHA-256 deduplication → S3 storage → document metadata → Celery → parse → 900-character chunks with 200-character overlap → deterministic 256-dimensional character-hash vectors → Qdrant → ready.

PDF pages and PPTX slides preserve their number. DOCX/HTML/plain text use a logical page 1; XLSX uses sheet number. These are not physical print page numbers. Original filenames and document IDs remain attached to each citation.

Errors mark documents as failed and are visible in the UI. Administrators can reindex. Parsing errors are not automatically retried. Scanned PDFs and images go through ClamAV and then local PaddleOCR PP-OCRv5 (Thai/English); nothing is sent to an external OCR service.

## Retrieval

The server first filters both document and chunk records to the signed-in tenant. It further limits by selected knowledge base and document IDs. The sparse side uses BM25 over English tokens and character trigrams (works with Thai without a language tokenizer). The dense side uses tenant-filtered Qdrant in Docker, and in-process dot products without Docker. Reciprocal Rank Fusion combines rankings. The hash embedding is a demonstration baseline; it does not infer semantic meaning like a trained multilingual embedding model.

There is no per-group or per-document ACL inside a tenant in this version: tenant members share that tenant's knowledge. Conversations are private to the owning user even within a tenant.

## Answering

Permission-aware retrieval → enabled LLM registry check → extractive demo or configured LiteLLM → persist conversation, answer, retrieval references, usage and audit event → stream NDJSON to browser. The provider call currently completes before browser streaming begins. Browser stop cancels display/transport; it does not promise provider-side cancellation or rollback of persisted answers.

No evidence returns an explicit uncertainty response with no citations. Demo references map directly to stored chunks. For real models, the UI displays retrieved context references; it does not yet verify that each generated claim is supported by each reference.

## Identity

Local password login uses Argon2. Opaque session tokens are random and only their SHA-256 digest is stored. Sessions last 24 hours from sign-in (`SESSION_HOURS`, 15 minutes to 30 days) and are revalidated against user and organization status per request. The OIDC adapter uses authorization code flow, PKCE S256, state cookie plus expiring server record, nonce, RS256 signature/JWKS, issuer and audience checks, verified email, and preprovisioned user mapping. Identity Provider roles cannot elevate local permissions.

Production disables demo by default and sets Secure cookies when `APP_ENV=production`. No public signup or automatic tenant provisioning exists.

## Tenant isolation in PostgreSQL

Besides the `tenant_id` checks in the API, PostgreSQL row-level security enforces isolation. The API and workers connect as the unprivileged role `hub_app` (`DATABASE_URL`); the owner role `hub` (`MIGRATION_DATABASE_URL`) runs migrations, `python -m hub.rls` and backups. `hub.rls` is idempotent: it enables a `tenant_isolation` policy on every table that has a `tenant_id` column. After authentication, USER and DEPARTMENT_ADMIN sessions are bound to their tenant (`app.tenant_id`), so a missed filter in the API still cannot read or write another tenant's rows (the write check is `WITH CHECK`). SUPER_ADMIN sessions and trusted system contexts (login, workers, scheduler) bypass the policy because they work across tenants. Verify with `docker compose exec -T api python -m hub.rls_check`.

## External integrations

Real S3 and Qdrant indexing/search plus Celery have been exercised in Docker. Real paid LLM providers, media APIs and advanced evaluation are not claimed as verified. SSO/HTTPS are not part of the intended deployment. See verification and limitations.

## Department-based self-service

A knowledge base has an owning department (`knowledge_bases.department_id`, an access group of kind `department`). Department admins create, edit, reindex and delete documents only in their own department's knowledge bases (a knowledge base with no department stays manageable by any department admin and Super Admins); plain users read but never write unless granted explicitly. `kb_sources` mirror an https file into a knowledge base: `hub.sync` re-fetches on an interval (from `maintenance_task`), adds a new version only when the content hash changed, and the normal ingest pipeline re-indexes it. Fetching refuses non-https, credentials, private/loopback addresses (re-checked after DNS and on every redirect).
