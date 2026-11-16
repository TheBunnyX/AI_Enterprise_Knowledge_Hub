# MASTER BUILD PROMPT
## AI Knowledge Hub — Super Enterprise AI RAG Platform

You are a Principal Software Architect, Senior Full-Stack Engineer, AI/RAG Engineer, DevOps Engineer, Database Architect, Security Engineer, and UI/UX Designer.

Build a real, working, Dockerized, enterprise-grade, multi-tenant AI Knowledge Platform named **AI Knowledge Hub**.

This must be an actual runnable application with real database persistence, API endpoints, authentication, AI integrations, document ingestion, RAG retrieval, admin operations, and automated tests.

Do not deliver only UI mockups, static dashboards, pseudocode, or incomplete scaffolding.

Use the attached UI reference images as the visual design specification.

All primary UI text must be in Thai, with English technical terminology where appropriate.

---

# 1. Core Requirements

Build two applications within one unified platform:

### Application A: Enterprise User Portal

Implement these screens:

1. Dashboard / Home
2. AI RAG Chat with citations
3. Enterprise Knowledge Search
4. AI Image / Video Studio
5. User Analytics, Usage and Settings

Additional user modules:

- My Documents
- Knowledge Bases
- File Upload
- Speech-to-Text
- Text-to-Speech
- Chat History
- Document Preview
- Account Settings

### Application B: Super Admin Console

Implement these screens:

1. Super Admin Overview Dashboard
2. Organization and User Management
3. AI Models and Services Management
4. Usage Monitoring and Billing
5. System Security and Settings

Additional management capabilities:

- Tenant Management
- Role and Permission Management
- Knowledge Base Administration
- Document Ingestion Monitoring
- AI Provider API Key Management
- Model Routing and Pricing
- System Health
- Audit Logs
- Backup Management
- Evaluation Dashboard

All screens must be responsive, fully navigable, and backed by actual APIs.

---

# 2. Mandatory Technology Stack

Frontend:
- Next.js App Router
- TypeScript strict mode
- React
- Tailwind CSS
- shadcn/ui
- Lucide Icons
- Recharts
- TanStack Query
- React Hook Form
- Zod
- Next.js server-side authentication integration

Backend:
- Python
- FastAPI
- Pydantic
- SQLAlchemy 2
- Alembic
- Celery
- Redis
- OpenTelemetry

Data:
- PostgreSQL
- SeaweedFS with S3-compatible API
- Qdrant Vector Database

Authentication:
- Keycloak
- OpenID Connect
- Role-Based Access Control
- Tenant-scoped authorization

AI:
- LiteLLM Gateway
- OpenAI API
- Anthropic API
- Google Gemini API
- Local embedding and reranking adapters

Quality:
- Pytest
- Vitest
- Playwright
- Ragas
- DeepEval

Infrastructure:
- Docker
- Docker Compose
- Multi-stage Dockerfiles
- Persistent named volumes
- Health checks
- Environment-based configurations

Use stable, mutually compatible dependency versions and pin production image versions. Check the actual provider model IDs before enabling a model.

---

# 3. Frontend Design System

Use a minimal enterprise SaaS design.

Visual style:
- White and soft-blue background
- Primary blue #2563EB
- Light blue #EFF6FF
- Slate text #0F172A
- Secondary text #64748B
- Soft gray borders #E2E8F0
- Green for healthy states
- Amber for warnings
- Red for errors
- Rounded cards
- Subtle shadows
- Generous spacing
- Professional typography

Use a Thai-compatible font such as Noto Sans Thai.

Global application shell:
- Left sidebar navigation
- Top search bar
- Notifications
- User avatar menu
- Role-based navigation
- Breadcrumbs
- Loading skeletons
- Empty states
- Error states
- Toast notifications
- Confirmation dialogs

Desktop-first for admin dashboards, fully responsive for tablet and mobile.

Follow the provided screenshots closely while improving accessibility and clarity.

Never use decorative UI elements that do not serve a clear purpose.

---

# 4. Enterprise User Dashboard

Route: /dashboard

Create:
- Greeting banner
- Global AI prompt box
- Quick access cards
- Recent documents
- Recently used knowledge bases
- Recent conversations
- AI usage summary
- Notifications

Quick access actions:
- Chat with Documents
- Search Knowledge
- Generate Images
- Generate Videos
- Speech-to-Text
- Text-to-Speech
- Summarize Document

Every action must navigate to a functional module.

---

# 5. AI RAG Chat

Route: /chat

Features:
- Streaming AI responses
- Conversation history
- Knowledge base selector
- File attachments
- Markdown rendering
- Source citations
- Citation click-to-preview
- Page numbers
- Relevant document snippets
- Model selector limited by tenant policy
- Copy response
- Regenerate answer
- Feedback buttons
- Stop generation
- Error recovery

Chat must call the real backend.

Implement a secure request flow:

Authenticate
→ Authorize tenant and user
→ Classify query
→ Plan retrieval
→ Retrieve permitted documents
→ Rerank results
→ Assemble grounded context
→ Select authorized LLM
→ Stream answer
→ Save conversation and citations

When no reliable evidence is available, communicate uncertainty rather than inventing citations.

---

# 6. Knowledge Search

Route: /knowledge/search

Features:
- Global search
- Keyword search
- Semantic search
- Hybrid search
- Document type filters
- Knowledge base filters
- Date filters
- Permission-aware results
- Relevance sorting
- Document previews
- Search result highlighting
- Pagination

Implement:

Dense Vector Search
+ Sparse / BM25 Search
+ Reciprocal Rank Fusion
+ Optional Reranking

Use Qdrant for vector retrieval and appropriate payload filters.

Do not expose documents from unauthorized tenants or user groups.

---

# 7. Document Ingestion and RAG Pipeline

Supported files:
- PDF
- DOCX
- PPTX
- XLSX
- TXT
- Markdown
- HTML
- CSV
- Images with OCR
- Audio transcription as an optional adapter

Document lifecycle:

Upload
→ Validate type and size
→ Scan file
→ Store original in SeaweedFS
→ Create document metadata in PostgreSQL
→ Queue ingestion job
→ Parse document
→ Extract structure and tables
→ OCR when necessary
→ Normalize content
→ Chunk document
→ Generate embeddings
→ Index in Qdrant
→ Mark as ready

Implement:
- SHA-256 deduplication
- Document versioning
- Retry and dead-letter handling
- Failed ingestion recovery
- Processing progress
- Idempotent jobs
- Document deletion
- Reindexing
- Knowledge base ACL
- Document ACL
- Source metadata preservation

Chunking strategies:
- Fixed-size baseline
- Heading-aware
- Semantic chunking
- Parent-child chunking
- Table-aware chunking

Document metadata must include tenant_id, knowledge_base_id, document_id, version, source, page number, timestamps, access scope, and embedding version.

---

# 8. Embedding and Reranking

Build a configurable model adapter architecture.

Embedding candidates:
- Qwen3 Embedding 8B
- BGE-M3
- OpenAI text-embedding-3-small

Reranking candidates:
- Qwen3 Reranker 8B
- VoyageAI rerank-3-lite

Requirements:
- Configurable embedding provider
- Configurable dimensions
- Embedding batch jobs
- Failed job recovery
- Embedding versioning
- Reranker abstraction
- Latency and cost metrics
- Evaluation support

Do not mix incompatible embedding spaces inside a single vector field.

For local development, allow a lightweight embedding model so the system can run without a GPU.

Large local models must be optional Docker profiles or remote inference services.

---

# 9. Multi-LLM Model Gateway

Integrate LiteLLM using provider adapters.

Provider groups:
- OpenAI
- Anthropic Claude
- Google Gemini
- Optional custom OpenAI-compatible endpoint

Implement a model registry with:

- Provider
- Real API model ID
- Display name
- Model category
- Input token price
- Output token price
- Context limits
- Enabled status
- Tenant availability
- Sensitivity restrictions
- Priority
- Fallback model
- Usage limits
- Pricing effective date

Support:
- Streaming
- Timeout
- Retry with backoff
- Circuit breaker
- Model fallback
- Per-tenant quotas
- Token accounting
- Request cost calculation
- Usage logs
- Provider health monitoring

Model IDs and prices must be dynamically configurable through the Super Admin Console.

Never assume that a proposed or future model name is an actual provider API identifier.

Create a decision-router interface for the requested Jev 1.14 model, but keep the implementation optional until an actual supported endpoint is configured.

Default routing must work deterministically using rule-based policies even without Jev.

Security and tenant authorization must never depend solely on an LLM decision.

---

# 10. AI Image, Video and Speech Studio

Routes:
- /studio/image
- /studio/video
- /studio/stt
- /studio/tts

Features:
- Prompt input
- Model selection
- Provider-specific options
- Job status
- Generation history
- Result preview
- Download
- Usage tracking
- Cost accounting

Use provider adapters to support configured image, video, STT, and TTS APIs.

Unavailable providers should be marked as not configured rather than falsely returning generated media.

Use asynchronous jobs for long-running media operations.

Store completed media in SeaweedFS with authorized access.

---

# 11. Super Admin Dashboard

Route: /super-admin

Show:
- Total organizations
- Total active users
- Total documents
- Total AI requests
- Monthly AI costs
- Provider cost breakdown
- Usage charts
- Model distribution
- Infrastructure health
- Recent audit events
- Top organizations by usage
- Error rates

All metric cards must be connected to actual backend queries.

Support date filters and tenant filters.

Do not display fictional numbers as real data.

---

# 12. Organization and User Management

Routes:
- /super-admin/organizations
- /super-admin/users

Features:
- Create organization
- Edit organization
- Suspend organization
- Organization details
- Tenant resource quotas
- Subscription plan configuration
- Organization API access policies
- User invitation
- User suspension
- Role assignment
- Group management
- Tenant-level admin assignment

Roles:
- SUPER_ADMIN
- TENANT_ADMIN
- KNOWLEDGE_MANAGER
- MEMBER
- VIEWER

Enforce tenant boundaries in every backend endpoint.

Super Admin must use explicit, audited administrative privileges.

---

# 13. AI Model Management

Route: /super-admin/models

Tabs:
- LLM
- Embedding
- Reranker
- STT
- TTS
- Image
- Video
- Search API

Features:
- Add provider
- Add model
- Edit model
- Enable or disable model
- Configure provider endpoint
- Configure secret reference
- Configure routing rules
- Configure pricing
- Configure fallback
- Test connection
- Review model usage
- Review error rate
- Review latency
- Review cost

Provider keys must never appear as plaintext in frontend responses.

Secret values must be stored securely, not in ordinary application logs.

---

# 14. Usage Monitoring and Billing

Route: /super-admin/billing

Implement:
- Cost overview
- Token usage
- Per-provider costs
- Per-model costs
- Per-tenant costs
- Cost per request
- Image/video generation costs
- Monthly budget
- Budget alerts
- Usage export
- CSV reports
- Cost estimation

Track:
- Input tokens
- Output tokens
- Cached tokens when supported
- Provider pricing version
- Actual reported usage when available
- Estimated cost when actual cost is unavailable

Clearly label estimates.

Build usage metering and internal chargeback first.

Actual customer payment collection must be a separate integration.

---

# 15. Security and Governance

Route: /super-admin/security

Implement:
- SSO configuration
- Roles and permissions
- Tenant isolation
- Document access policies
- Audit logs
- Session management
- API key management
- Security event review
- Data retention configuration
- Backup status
- Restore operations restricted to authorized admins

Security requirements:
- OIDC authentication
- Server-side authorization
- PostgreSQL row-level security where appropriate
- Tenant-scoped queries
- Qdrant tenant filters
- Private SeaweedFS buckets
- Presigned file access
- File type and size validation
- Rate limiting
- Request validation
- Audit logging
- Prompt injection defense
- Secrets management
- No hardcoded production credentials
- No secrets inside Next.js public environment variables

Create tests proving that tenant A cannot retrieve tenant B's documents, vectors, conversations, or media.

---

# 16. Database Design

Use PostgreSQL with Alembic migrations.

Required entities:

- organizations
- organization_settings
- users
- memberships
- roles
- permissions
- groups
- knowledge_bases
- knowledge_base_permissions
- documents
- document_versions
- document_chunks
- document_permissions
- ingestion_jobs
- embedding_jobs
- conversations
- messages
- message_citations
- ai_providers
- ai_models
- model_routes
- model_prices
- usage_events
- billing_periods
- quotas
- generation_jobs
- media_assets
- audit_logs
- system_settings

Use UUID primary keys where appropriate.

Add tenant_id, timestamps, indexes, foreign keys, soft-delete policy, and uniqueness constraints.

Apply authorization checks to all tenant-scoped resources.

Do not store huge files or embedding vectors directly in PostgreSQL when they belong in SeaweedFS or Qdrant.

---

# 17. Docker Architecture

Create a Docker Compose environment with:

- web: Next.js
- api: FastAPI
- worker: Celery
- postgres: PostgreSQL
- redis: Redis
- qdrant: Qdrant
- seaweedfs: SeaweedFS with usable S3 API
- keycloak: Identity provider
- litellm: Model gateway
- monitoring services under optional profiles

Use separate internal Docker networks where appropriate.

Requirements:
- Production-style multi-stage Dockerfiles
- Next.js standalone output
- Named persistent volumes
- Health checks
- Dependency readiness handling
- Environment configuration
- Restart policies
- Graceful shutdown
- Database migrations
- Initialization scripts
- Non-root application containers
- No exposed database/vector/storage/admin ports in production by default

Provide working development configuration and a separate production-oriented configuration.

Do not expose Keycloak bootstrap or development administration settings publicly in production.

Docker Compose is the initial deployment target, not an automatic guarantee of high availability.

---

# 18. Repository Structure

Use a monorepo layout:

ai-knowledge-hub/
  apps/
    web/
    api/
    worker/
  packages/
    ui/
    types/
    config/
  infrastructure/
    docker/
    keycloak/
    monitoring/
  scripts/
  tests/
  docs/
  compose.yaml
  compose.prod.yaml
  .env.example
  README.md

Structure the backend by domains rather than putting everything into a single main.py.

Use reusable frontend components and consistent design tokens.

---

# 19. Docker Setup and Local Development

Implement these commands:

docker compose config

docker compose up -d --build

docker compose ps

docker compose logs -f

docker compose down

Provide a Makefile with:

make up
make down
make logs
make migrate
make seed
make test
make lint

Create .env.example with all required configuration variables and safe placeholders.

Never commit actual API keys, passwords, or secrets.

After Docker startup, the user should be able to:

1. Open Next.js in the browser.
2. Log in with a documented development account.
3. Access the Enterprise User Portal.
4. Access Super Admin with an authorized role.
5. Create a tenant.
6. Create a knowledge base.
7. Upload a PDF.
8. Process and embed its content.
9. Ask a question about the PDF.
10. Receive an answer with valid document citations.
11. Inspect usage and audit logs.

If no paid LLM key is configured, provide a clearly labeled demonstration mode with deterministic answers based on seeded examples.

Never pretend that mock output is a real provider response.

---

# 20. Testing and Quality Gates

Create automated tests for:

Frontend:
- Component rendering
- Navigation
- Form validation
- Role-aware UI
- Error and loading states

Backend:
- Authentication
- Authorization
- Tenant isolation
- API validation
- Document ingestion
- Retrieval filters
- Citation mapping
- Model routing
- Cost calculation
- Audit events

Integration:
- PostgreSQL migrations
- SeaweedFS upload/download
- Qdrant indexing/search
- Redis/Celery task execution
- LLM gateway adapter
- Docker health

End-to-end:
- Login
- Create organization
- Upload document
- Wait for processing
- Ask RAG question
- View citation
- Review usage

Include Ragas and DeepEval evaluation scripts with a small reproducible example dataset.

Report actual executed test results.

---

# 21. Implementation Order

Build incrementally in the following order.

PHASE 1:
- Monorepo
- Docker Compose
- Next.js
- FastAPI
- PostgreSQL
- Authentication
- Design system
- Shared application layout

PHASE 2:
- Super Admin Dashboard
- Organization management
- User management
- Tenant isolation
- Database schema
- API endpoints

PHASE 3:
- SeaweedFS
- Knowledge base management
- Document upload
- Ingestion worker
- Parsing
- Embeddings
- Qdrant
- Hybrid retrieval

PHASE 4:
- RAG Chat
- Streaming responses
- Citations
- Multi-LLM gateway
- Model registry
- Usage metering

PHASE 5:
- Model administration
- Billing analytics
- System monitoring
- Security console
- Evaluation dashboard

PHASE 6:
- Image/video generation
- STT/TTS
- Extended testing
- Performance optimization
- Production hardening

Complete and verify each phase before moving to the next.

---

# 22. Required Final Deliverables

Deliver:
1. Actual complete source code.
2. Working Next.js application.
3. Working FastAPI application.
4. PostgreSQL schema and migrations.
5. SeaweedFS integration.
6. Qdrant integration.
7. Docker Compose files.
8. Dockerfiles.
9. Environment template.
10. Seed data and development setup.
11. Authentication and authorization.
12. Functional RAG flow.
13. User Portal UI.
14. Super Admin UI.
15. Test suite.
16. README and deployment documentation.
17. Architecture documentation.
18. OpenAPI documentation.
19. Model configuration documentation.
20. Known limitations and production-readiness checklist.

Avoid placeholders for core functionality.

If a feature depends on an unavailable external credential or GPU, implement and test its interface and clearly mark it as requiring configuration.

Do not claim an integration is functional without testing it.

Start by inspecting the workspace, then produce the repository structure and implement Phase 1. Continue through the phases as far as the available execution environment permits.

Prioritize running code, working database operations, secure tenant boundaries, and reproducible Docker startup over decorative frontend features.
