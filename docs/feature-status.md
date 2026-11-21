# Latest feature status

The web UI is at **http://localhost:3009** (or http://127.0.0.1:3009) and the API docs at http://localhost:8100/docs. Existing data is kept. Roles are SUPER_ADMIN, DEPARTMENT_ADMIN and USER. The platform serves a single organisation.

## Recent additions

- PostgreSQL + documents, versions and media backed up with AES-256-GCM every 24 hours, 7 sets kept, downloadable and restorable from Super Admin, with a safety snapshot before data is replaced. A first-start seed restore (`SEED_BACKUP_URL`) can load a backup into an empty database.
- Departments and groups with read and write permissions per knowledge base and document, enforced in search, chat, download and PDF.
- ClamAV scans before parser, OCR and storage; files are rejected when the scanner is not ready.
- Persistent job queue with unique keys, renewable leases and recovery every 60 seconds. Media jobs that may already be billed need confirmation before a retry.
- A bell for service and failed-job alerts, filtered by permission, with read state and recovery notices.
- Original PDF with page change, zoom and highlighting of the cited text on pages that have a text layer.
- Conversation sharing inside the organisation by user or group with an expiry. A recipient needs access to every cited document, and this is rechecked on every open.

## Working core features

| Area | What works |
| --- | --- |
| Users and organisation | Edit the organisation, suspend users, add accounts, change roles, per-user quota per day / week / month, model policy and budget |
| Sign-in | Argon2 and HttpOnly sessions, sign-out, edit name / default model / notifications, change a local password, view and revoke sessions, OIDC code + PKCE adapter |
| Knowledge bases | Create and edit; open to everyone in the organisation or restricted to users; separate read and upload rights; enforced in the API, search, download and chat |
| Chat attachments | A paperclip attaches PDF, DOCX, PPTX, XLSX, TXT, MD, CSV, HTML, PNG/JPG (up to 5 files, 20 MB). Text is read (images via OCR), kept temporarily for that user only, not indexed, and sent to the LLM up to `CHAT_ATTACHMENT_CHARS` characters. Works with and without documents. Legacy .doc / .xls are not supported (save as DOCX / XLSX) |
| Documents | PDF, Office, text and image upload, SHA-256 deduplication, S3, Celery queue, reindexing, versions and old-version download, trash and restore |
| OCR | PaddleOCR (PP-OCRv5) Thai and English plus pypdfium2 in Docker for images and scanned PDF pages; PDFs limited to 200 pages and 20 MB |
| Search | BM25 (Thai tone marks ignored) + KB-filtered Qdrant + RRF, embedding `local:multilingual-e5-small` and reranker `local:bge-reranker-v2-m3` (ONNX on CPU) or through a gateway, separate collection per model / dimensions / version |
| RAG | SSE from the gateway → NDJSON → UI, stop generation, history and conversation context, citations pinned to the original document version, feedback, fallback model permitted by the organisation |
| AI services | URL and API key in the UI, keys encrypted with Fernet, test `/models` and list model IDs, enable or disable models, set prices |
| Media | Image / Video / STT / TTS through a LiteLLM-compatible API, background jobs, status and progress, cancel and retry, results stored in S3, preview and download for the owner only |
| Reports | Real activity, tokens and estimated cost, budgets and budget status, unpriced media jobs are not shown as free, CSV export by period, audit log |

## Turning on real AI

1. Go to Super Admin → AI models and services.
2. Enter a gateway URL that the API and worker can reach, for example your own gateway or `http://host.docker.internal:4000/v1` for a service on the Docker Desktop host.
3. Enter the API key and save. It is encrypted and never returned as readable text.
4. Run the connection test to see the model IDs the gateway returns.
5. Add models in the right category (LLM / Image / Video / STT / TTS) and enable them.
6. Set the models the organisation allows on the organisation page, then pick a model in chat or Studio.

The system never enables a guessed model name and never calls a paid service without your configuration. No provider key was available, so the network adapters were tested with mocked responses, while Docker, PDF, OCR, S3, Qdrant and Celery use real services.

## Real embeddings and reranker

Set `EMBEDDING_MODEL` to a real gateway alias, `EMBEDDING_DIMENSIONS` to match the output and `EMBEDDING_VERSION` to the index version, then recreate the API and worker and reindex. Search never mixes chunks from an old embedding version. Set `RERANK_MODEL` if the gateway has a `/rerank` model; a name in the registry page alone does not change the retrieval adapter.

The default is still the CPU hash embedding and a labelled extractive demo answer. Choose a real LLM in chat to call a provider.

## Limits to address before production

- No DLP, 2FA policy, TLS ingress, HA, OpenTelemetry or Ragas/DeepEval dashboard. Row-level security is present (see [limitations](limitations.md)).
- OIDC and paid AI / media have not been tested with real provider accounts.
- Cancelling a job may not stop upstream billing. Video status checks last at most 15 minutes and can resume from the same provider job ID.
- A media job whose provider reports no price shows "provider has not reported"; a budget cannot include costs that are unknown.
- Chat reserves budget as an estimate before calling the LLM and corrects it with reported tokens when available. There is no circuit breaker or invoice reconciliation.
- The trash keeps files with no automatic retention or purge. Backups stay on the same machine; copy them off the machine and keep the key separately.
- OCR depends on image quality, and table or image positions are not shown as the original in the text preview.
- The learned embedding and reranking adapters were tested with mocks; a real model must support the gateway protocol.

See verification.md for real test results. This document is the latest status and supersedes the notes from the first delivery.
