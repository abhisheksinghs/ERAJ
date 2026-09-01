# Eraj — Backup & Restore

## What is backed up

- **Postgres** — DigitalOcean Managed Postgres **PITR**, retention 14 days
  (raise to 30 before onboarding paying customers). This is the only
  authoritative store.
- **Redis** — cache + Celery broker only. **Not backed up.** Nothing
  authoritative may be written to Redis; if that ever changes, this doc and the
  backup policy change with it.
- **Uploaded files** — none yet. When a module adds uploads (S3/Spaces),
  enable versioning + lifecycle and add it here.

## Monthly restore drill  (do not skip — an untested backup is not a backup)

1. Restore the latest PITR snapshot to a **scratch** database instance.
2. `python manage.py migrate_schemas --check` against it — schema is intact.
3. Row-count spot check on `public.core_client`, `public.core_subscription`,
   and one tenant's `library_book`.
4. Tear down the scratch instance.
5. Record the date + result in the ops log.

## Single-tenant restore

To recover one tenant without touching the others:

```bash
# from a scratch instance restored to the target point in time
pg_dump --format=custom --schema='<schema_name>' -f tenant.dump "$SCRATCH_DB_URL"

# into production, after dropping/renaming the damaged schema
pg_restore --schema='<schema_name>' -d "$PROD_DB_URL" tenant.dump
```

The tenant's `Client`/`Subscription` rows live in `public` — restore those
separately only if they were also lost.

## Full disaster recovery

1. New Managed Postgres from PITR (or the latest daily snapshot).
2. Repoint `DB_HOST` (App Platform env) → redeploy.
3. `celery-beat` catches up the daily recompute on its next run; no manual step.
4. Redis comes up empty — caches refill on demand, in-flight Celery tasks are
   lost (acceptable: the daily recompute is idempotent, re-run it manually if
   the outage crossed 00:05 IST).
