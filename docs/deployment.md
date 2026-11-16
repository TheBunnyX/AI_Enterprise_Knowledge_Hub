# Deployment and identity

## Development

`scripts/setup-env.ps1` creates random local service secrets in ignored `.env`. Run `docker compose up -d --build` after configuration. API startup waits for PostgreSQL and S3, runs Alembic, then starts FastAPI. Demo seed data are created once when the organization table is empty. API and web have readiness checks; worker starts after API readiness.

Back up PostgreSQL and SeaweedFS together, plus Qdrant if preserving the current index is required. Indexes can be rebuilt from originals. `docker compose down` preserves volumes. No automated backup or restore process is implemented.

The current application containers run as UID 10001. Infrastructure vendor images retain their vendor defaults. All services currently share a Compose network; production network segmentation is still required.

## Production-oriented baseline

Use a fresh database rather than repurposing demo data as production. Then:

```powershell
docker compose -f compose.yaml -f compose.prod.yaml config --quiet
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
docker compose exec api python -m hub.provision_admin
```

The interactive one-time provisioner creates the first local administrator and organization. It reads the fallback password without echo and refuses to run when an admin exists. Local password login remains disabled in production unless deliberately setting `ALLOW_LOCAL_LOGIN=true` in the API environment. Never expose a demo deployment or the Keycloak `start-dev` service publicly.

The API runs as the `hub_app` database role (row-level security); migrations and backups use the owner role from `MIGRATION_DATABASE_URL`. No hosting registration or internet publication has been performed: Sites' Worker runtime cannot host this multi-container Python/PostgreSQL architecture directly.

Before real users, complete the security, ACL, reliability, provider, monitoring and backup work in `limitations.md`. Compose is a reproducible single-host deployment, not a high-availability guarantee.
