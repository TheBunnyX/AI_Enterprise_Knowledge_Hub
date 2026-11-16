# Latest verification — 31 October 2026, Asia/Bangkok

- Backend: **48 tests passed** (one dependency deprecation warning).
- Frontend: **10 tests passed** in three suites; strict TypeScript check passed.
- Docker optimized Next.js build passed; Alembic is at **0003 (head)** and preserved the existing database.
- Real ClamAV clean stream + EICAR rejection passed. Encrypted snapshot was restored into an isolated temporary PostgreSQL database and S3 prefix; document count and all **9 original files** verified by SHA-256. Temporary targets cleaned afterward. **No live restore performed.**
- Celery Beat produced a completed automatic snapshot; all six monitored services reported healthy. Real PDF canvas rendering and yellow citation highlighting verified in browser; restore-plan dialog disabled final action until matching confirmation.
- Added tests for group/document ACL and revocation, cross-tenant membership rejection, shared-chat access after file permission changes, duplicate job admission, expired lease recovery, ambiguous media review, notification dedup/read state, encrypted archive tampering, PDF authorization and super-admin operations restrictions.
- Real Docker integration passed: PostgreSQL persistence, Celery PDF ingestion, **image OCR (Tesseract at the time; now PaddleOCR PP-OCRv5 Thai, re-checked in Docker on a Thai test image)**, byte-for-byte SeaweedFS storage, Qdrant tenant-filtered indexing/search, hybrid retrieval, streamed demo answer, page citation, authenticated download and usage/audit records.
- Added negative tests: KB read/write ACL, cross-tenant ACL assignment rejection, version history/download/preview, trash/restore, encrypted API key/no plaintext response, owner-only media access, failed media without secret leakage, account/session revocation, model allowlists, feedback ownership, filtered CSV export.
- Provider protocol tests use mocked HTTP responses for image/video/STT/TTS, true SSE LLM deltas/token usage, embedding dimensions/version separation and reranking. These are **not live paid provider tests**.
- `npm audit --omit=dev`: no vulnerabilities found; full Docker npm install audit also reported zero after updating Vitest to 5.0.5.
- Web port changed to **3009**, internal container port remains 3000. API remains loopback port 8100.

Live Keycloak and paid provider credentials, production TLS/load testing, offsite disaster recovery and evaluation frameworks remain unverified. PDF scan OCR has no spatial highlight overlay. The earlier record below describes the first delivery and is retained as history.

---

# Verification record

Date: 31 October 2026 (Asia/Bangkok). Environment: Windows, Node.js 22+, Python 3.12, Docker Desktop Linux engine. This document records executed checks, not intended future checks.

| Check | Result |
| --- | --- |
| Backend Pytest | **21 passed**, one dependency deprecation warning |
| Frontend Vitest | **4 passed**: login fields/configuration, member navigation, admin navigation, API error handling |
| TypeScript strict check | Passed |
| Next.js optimized build | Passed locally and in multi-stage Docker image |
| Compose development configuration | Passed with `docker compose config --quiet` |
| Compose production overlay configuration | Passed syntax/configuration validation; not deployed as production |
| Docker API, PostgreSQL and Redis health checks | Healthy |
| Docker web health check | Healthy at final handoff |
| SeaweedFS S3 | Actual PDF upload/read round trip verified byte for byte |
| Celery / Redis | Uploaded PDF processed by the separate worker into ready status |
| Qdrant | Actual upsert/query, document filter and negative tenant filter checked |
| Hybrid retrieval | Uploaded unique PDF text found through authenticated API |
| Demo chat | NDJSON response and persisted conversation, valid document/page-1 reference |
| Download | Authenticated API returns identical original PDF bytes |
| Metering/audit | Request count and audit records populated from performed actions |
| OIDC | Mocked OIDC server with real RSA-signed ID token, state, nonce, audience/issuer and PKCE checks; local role cannot be elevated through ID token claims |

Backend negative tests cover unauthenticated access, member/admin boundary, viewer read-only behavior, cross-tenant document/download/search/conversation access, CSRF origin rejection, missing provider, file validation and quota enforcement. A mocked gateway test verifies request context, provider token counts and configured-price cost estimation. Parser tests exercise DOCX, PPTX and XLSX; integration check generates and processes a real PDF.

Browser checks were performed through the in-app browser against the running application: demo login, dashboard navigation, chat response, source click-to-preview, admin overview, organization list and form, desktop and 390 × 844 mobile layout/menu. Saved screenshots are in `docs/screenshots/`.

## Reproduce

```powershell
cd apps/api
../../.venv/Scripts/python.exe -m pytest -q
cd ../web
npm.cmd run test
npm.cmd run typecheck
npm.cmd run build
cd ../..
docker compose config --quiet
docker compose -f compose.yaml -f compose.prod.yaml config --quiet
docker compose exec -T api python -m hub.integration_check
docker compose ps
```

The Docker integration check uses the current Compose application's demo tenant and adds a uniquely marked PDF plus conversation/usage/audit records. It is for a development database only. It does not call paid AI services.

## Not verified

External LiteLLM or paid provider outputs; antivirus; actual image/video/audio generation; Ragas/DeepEval; load/concurrency resistance; backup/restore. PostgreSQL row-level security was verified on the live Docker database with `hub.rls_check` (cross-tenant read and write blocked). These remain limitations, not successful integrations.

An initial test run hit Windows execution-environment filesystem restrictions; the test directory was moved under the project and the tests were rerun successfully. An existing service occupied port 8000, so this project exposes its API at loopback port **8100** without altering that service.
