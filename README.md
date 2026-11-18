# AI Knowledge Hub

A multi-tenant, Thai-first enterprise knowledge platform: upload company documents, search them with hybrid retrieval, and ask questions that are answered **with page-level citations**. It ships with a user portal, a Super Admin console, role- and group-based access control, PostgreSQL row-level security, and LLM observability.

![Dashboard](docs/screenshots/preview.jpg)

## Why this project

Most RAG demos stop at "embed, retrieve, prompt". This project focuses on what an organisation actually needs before it can trust such a system:

- **Tenant isolation that does not depend on a single `WHERE` clause.** Every request is filtered by tenant in the API, and PostgreSQL row-level security enforces the same boundary underneath, so a forgotten filter cannot leak another tenant's rows.
- **Answers you can verify.** Each answer cites the document and page, the original PDF opens with the cited passage highlighted, and a citation checker re-points `[n]` markers to the passages that really support each statement.
- **Thai language support end to end.** Trigram BM25 works without a Thai tokenizer, a multilingual embedding model runs locally on CPU, and OCR for scanned Thai documents runs on-premises.
- **Cost and quality controls.** Per-model policies and budgets, answer and embedding caches, fallback models, and a measurable retrieval evaluation suite.

## Features

**Knowledge management**
- Upload PDF, DOC/DOCX, PPT/PPTX, XLS/XLSX, TXT, MD, CSV, HTML, PNG and JPEG (up to 20 MB) with SHA-256 de-duplication, document versions, trash and restore
- Asynchronous ingestion (Celery): parse, chunk (900 characters, 200 overlap), embed, index
- Local OCR for scanned PDFs and images (PaddleOCR PP-OCRv5, Thai and English)
- ClamAV scanning before a file is read or stored; uploads are refused if the scanner is down
- Scheduled mirroring of https sources, re-indexed only when the content hash changes

**Search and chat**
- Keyword (BM25), vector, and hybrid search with Reciprocal Rank Fusion, plus an optional cross-encoder reranker
- Chat that answers from documents with citations, or talks to a general model; per-question file attachments (not indexed, virus-scanned)
- Agent mode built on LangGraph: the model plans, calls tools (including web search), and can pause for a human clarification that survives restarts
- Streaming responses, Markdown and LaTeX rendering, fallback models when a provider returns 429/5xx
- Multiple providers behind one gateway: Google AI, OpenRouter, LiteLLM, and a local Qwen model

**Governance and operations**
- Roles: Super Admin, Department Admin, User; knowledge-base and document ACLs by user, department or group
- OIDC sign-in (authorization code + PKCE), Argon2 password hashing, hashed opaque session tokens
- Encrypted provider API keys, audit log with CSV export, usage and cost reports
- Encrypted automatic backups with tested restore, background-job recovery, in-app alerts
- Optional self-hosted **Langfuse** tracing of retrieval and generation, with a switch to keep content out of traces

## Architecture

![System architecture](docs/architecture.svg)

Further reading: [architecture](docs/architecture.md) · [model configuration](docs/model-configuration.md) · [deployment](docs/deployment.md) · [operations](docs/operations.md) · [limitations](docs/limitations.md)

### Design decisions worth noting

| Decision | Reason |
| --- | --- |
| PostgreSQL only, no SQLite mode | Row-level security and migrations then behave identically in development, tests and production |
| App connects as the unprivileged `hub_app` role; migrations and backups use the owner role | A compromised request path cannot disable its own isolation policy |
| BM25 over character trigrams plus dense vectors, fused with RRF | Strong Thai retrieval without a language-specific tokenizer |
| Opaque session tokens, only the SHA-256 digest stored | A database leak does not yield usable sessions |
| Original files are served through an authenticated endpoint, always as attachments | The object-storage bucket is never public |
| Retrieval quality measured offline, with no LLM call | Chunking and embedding changes can be compared and gated in CI |

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript (strict), React Query, Recharts, Vitest |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Celery, LangGraph |
| Data | PostgreSQL 17, Qdrant, Redis, SeaweedFS (S3 API) |
| ML | `intfloat/multilingual-e5-small` and `bge-reranker-v2-m3` via ONNX Runtime (CPU), PaddleOCR |
| Security | Argon2, OIDC/PKCE, ClamAV, PostgreSQL RLS, encrypted secrets |
| Observability | Langfuse (self-hosted, optional), audit log, health and alert monitoring |
| Delivery | Docker Compose (development, production baseline, Langfuse overlay) |

## Getting started

**Prerequisites:** Docker with Compose v2 (a version that supports `!override` / `!reset`), roughly 8 GB of RAM allocated to Docker. Python 3.12 and Node.js 22+ are only needed to run outside Docker.

```bash
# 1. Create .env with random secrets (never overwrites an existing file)
./scripts/setup-env.ps1            # PowerShell; on Linux/macOS use: pwsh ./scripts/setup-env.ps1

# 2. Build and start the stack
docker compose up -d --build

# 3. Open the app
#    Web:     http://localhost:3009
#    API docs: http://localhost:8100/docs
```

The web UI and API bind to `127.0.0.1` only; all other services have no host ports.

Development accounts are created when `DEMO_MODE=true`: `admin@local.test` (Super Admin), `department@local.test` (Department Admin) and `member@local.test` (User). The random password is written to `/data/dev-password.txt` inside the API container. No production password is committed to the repository.

### Optional: LLM observability with Langfuse

```bash
./scripts/setup-langfuse.sh
docker compose -f compose.yaml -f compose.langfuse.yaml up -d
# UI: http://localhost:3100  (credentials are in .env as LANGFUSE_INIT_*)
```

### Common commands

```bash
make up            # build and start
make migrate       # alembic upgrade head
make seed          # sample organisation, accounts and documents
make test          # backend test suite (needs the dev Postgres port, see below)
make lint          # strict TypeScript check
make eval          # retrieval evaluation, fails if hybrid hit@k drops below 0.9
make eval-answers  # answer quality with Ragas (calls a judge LLM)
```

## Testing and evaluation

```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d postgres   # exposes Postgres on 127.0.0.1 only
make test                                                           # 214 backend tests passing
cd apps/web && npm run typecheck && npm run test && npm run build
docker compose exec -T api python -m hub.integration_check          # real Postgres, S3, Qdrant, Celery
docker compose exec -T api python -m hub.rls_check                  # verifies row-level security
```

- Backend tests run against a throwaway database and cover tenant isolation, ACLs and revocation, upload validation, ingestion recovery, backups, provider protocols (mocked HTTP) and Langfuse tracing.
- The retrieval evaluation (`apps/api/eval`) indexes a corpus through the real pipeline and scores 125 questions with **hit@1, hit@k, MRR and doc@k** for each search mode. It calls no LLM and nothing leaves the machine.

## Project structure

![Repository structure](docs/project-structure.svg)

<details>
<summary>Plain-text tree</summary>

```text
apps/web/              Next.js App Router frontend (Thai UI)
apps/api/hub/          FastAPI app: auth, ingestion, retrieval, chat, agent, admin, backups
apps/api/migrations/   Alembic migrations
apps/api/eval/         Retrieval and answer-quality evaluation
apps/api/tests/        Backend tests
infrastructure/docker/ Multi-stage, non-root images
scripts/               Environment and Langfuse setup, local startup
docs/                  Architecture, configuration, operations, verification, limitations
compose*.yaml          Development, dev overrides, production baseline, Langfuse
```

</details>

## Project status and limitations

This is a working system for development and integration, **not a production-certified product**. The repository states its gaps openly in [docs/limitations.md](docs/limitations.md). The main ones:

- Real paid LLM and media providers are covered by mocked protocol tests, not by live paid calls
- Backups live on the same host unless copied off-machine; no offsite replication or HA
- BM25 loads authorised chunks into memory, so very large corpora need a different approach
- Sign-in rate limiting is process-local; production needs distributed controls, CSP, a secret manager and TLS/SSO in front (`compose.prod.yaml` is a baseline only)
- Citations are checked against retrieved passages, but claim-level faithfulness of real model output is not proven

## What this project demonstrates

Full-stack product engineering (Next.js, FastAPI, Celery), retrieval-augmented generation with measurable quality, multi-tenant security design down to the database layer, asynchronous job processing with recovery, LLM cost and observability tooling, and a habit of documenting verification and limitations honestly.

## License

Released under the [MIT License](LICENSE).
