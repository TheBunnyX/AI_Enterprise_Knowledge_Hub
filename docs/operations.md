# Backups, permissions and background work

## Backups

Super Admin → Backup and restore shows service status, jobs and backups. Press "Back up now" to create a set, or download the `.akh` file, which is encrypted with AES-256-GCM.

By default a backup runs every 24 hours and 7 sets are kept; change this with `BACKUP_INTERVAL_HOURS` / `BACKUP_RETENTION` in the Compose environment. The key is `BACKUP_ENCRYPTION_KEY`, falling back to `SECRETS_KEY`. Keep the original key and the configuration file safely and separately: rotating the key makes older sets unreadable without the old key.

A backup covers PostgreSQL and the files in S3, including old versions and media. It does not include `.env`, TLS certificates or the Qdrant index, which is rebuilt from the documents. The `backups-data` volume lives on the same machine, so download or copy sets off the machine to survive a machine failure.

Before restoring, press "Verify / restore", check the backup time and file count, and type that set's confirmation text. The system stops new writes, waits until no job or chat is running, takes a safety snapshot and then restores in one transaction. If any job is still running the restore is refused. Media jobs in the backup do not resubmit themselves; after it finishes, check the status and sign in again.

Rehearse a restore in isolation with `docker compose exec -T api python -m hub.ops_integration_check`. It creates a current backup, restores it into a temporary PostgreSQL database and a separate S3 prefix, checks the document count and file hashes, then deletes only the test targets. It does not replace the live database.

## Permissions and sharing

The Documents and Knowledge pages have departments, groups and members. Pick a knowledge base or a document to set read or write access. A restricted document adds to the knowledge base's restriction, so a recipient must pass both layers. Administrators and knowledge managers can always reach everything in the organisation to manage it.

In chat, choose "Share within the organisation", pick users or groups and an expiry of 1–90 days. A share is read-only and never adds document access. When access to a cited document is withdrawn, the conversation is no longer opened for the recipient.

## Antivirus and job recovery

ClamAV checks a file before the parser, OCR or storage. If the service is down, uploads are refused, so ClamAV must have downloaded its signatures and be ready before uploading. A dangerous file is rejected, the administrator is notified and the file is not stored.

The system checks job leases every 60 seconds and retries ingestion at most 5 times. A media job whose state is unclear shows "Needs review". Check the result at the provider before retrying, because a retry may be billed again. A video with a provider job ID resumes checking that same job.

The bell shows alerts according to permission, with a recovery notice. It is not external monitoring: if the database, the API or the whole machine is down, the alerts page cannot be opened.

The original PDF opens from a document or a chat citation. A text layer can be highlighted; a scanned page with no text layer shows the original with the OCR in the text tab. OCR positions are not highlighted on the image.

## Deploy from GitHub with only env vars (Dokploy)

1. On the source machine: Admin → Backups → create a backup and download the `.akh` file. Host it at a private HTTPS URL
   (for example a private GitHub release asset or object storage with a token).
2. In Dokploy create a Compose service from the GitHub repo with Compose path `./compose.dokploy.yaml` (it includes `compose.yaml` and `compose.prod.yaml`), and set env vars only:
   `POSTGRES_PASSWORD`, `SECRETS_KEY` (both identical to the source), `WEB_ORIGIN=https://<your-domain>`,
   `WEB_BIND=<address the tunnel reaches>`, `SEED_BACKUP_URL`, `SEED_BACKUP_TOKEN` (optional), plus the provider keys from `.env`.
3. Deploy. On first start the API restores the snapshot into the empty database, rebuilds the search index, and writes
   `/data/.seed-restored` so it never runs again. Existing data is never overwritten.
4. Change the demo account passwords afterwards (`DEMO_ACCOUNTS` stays empty in production).

`POSTGRES_PASSWORD`, `SECRETS_KEY` and `BACKUP_ENCRYPTION_KEY` must not change after the data is restored, because the database roles and the encrypted provider keys depend on them.
