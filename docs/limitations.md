# Current limitations

The main features are in place (see [feature status](feature-status.md)), but this is not a certification that every production requirement of the master prompt is met.

- Per-user, per-department, per-group and per-document ACLs are enforced in the API, and PostgreSQL row-level security isolates rows by `tenant_id` (users and department admins). The platform serves a single organisation. Super Admin and background jobs bypass the policy, and RLS does not separate users or departments inside the organisation (the API ACLs do that).
- Docker scans uploads with ClamAV before reading or storing a file and stops accepting files when the scanner is down. There is no parser sandbox isolation and no DLP.
- LLM streaming and fallback, embeddings, reranker and all four media categories have adapters, but there were no paid provider credentials to test them for real. Several providers are supported (Google AI, OpenRouter, LiteLLM), each with its own API key; none was tested with a real key, and there is no RPM/RPD limiter on our side (a fallback model is used on HTTP 429).
- Budgets use reported tokens and administrator-defined prices, plus any media price the upstream reports. Unknown media cost is not counted as confirmed spend. There is no payment collection and no invoice reconciliation.
- A fallback model tries one permitted model before any text is sent. There is no full circuit breaker and no latency-based router.
- Stopping a chat or media job does not guarantee that the provider stops charging; some jobs may already be finished upstream.
- Encrypted database and file backups run every 24 hours and keep 7 sets in a Docker volume on the same machine. Copy them off the machine and keep the key separately to survive a machine failure. There is no offsite replication and no schedule or retention setting in the web UI.
- Restore was rehearsed into a separate PostgreSQL database and storage prefix. The Qdrant index is rebuilt after a live restore.
- Ingestion jobs have leases, recovery and bounded retries. A media job whose provider state is unknown needs an administrator to check and confirm; exactly-once cannot be guaranteed where the provider has no idempotency.
- PDFs are highlighted on the original for pages with a text layer. Scanned PDF pages show the original and the OCR text in separate tabs; there is no OCR bounding-box overlay.
- Alerts live inside the system. If the database, the API or the whole machine is down, alerts cannot be viewed, so production needs external monitoring.
- Search loads the permitted chunks into memory to compute BM25; this needs tuning for a large corpus.
- Citations link to the stored page and version, but the correctness of every claim has not been proven with a real model.
- The sign-in rate limit is process-local; production needs distributed controls, a CSP, a secret manager and network segmentation.
- No HA, infrastructure resource monitoring, OpenTelemetry, Ragas/DeepEval or evaluation dashboard.
- The initial migration refers to the current metadata; freeze its definitions before relying on the schema history in long-lived production.

Development data stays in Docker named volumes, and the web service binds to loopback on port 3009 (`WEB_BIND` changes the address) without being published to the internet.

- There are three roles: Super Admin (whole system), department admin (`DEPARTMENT_ADMIN`) and user (`USER`). A department admin sees and manages what the ACLs and groups they belong to allow, and edits members only in their own departments or groups. Knowledge bases are not owned by a department directly, a knowledge base open to the whole organisation is writable by every role, and there is no read-only role.
- Production-like test mode (`DEMO_MODE=false`, `APP_ENV` not `production`): no passwordless sign-in button, no sample data, and `extractive-demo` is disabled. The three test account passwords are in `/data/test-accounts.txt` inside the API container. Real use needs `compose.prod.yaml`, which requires HTTPS and SSO.
