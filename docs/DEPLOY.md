# Eraj — Deployment

Target: **DigitalOcean App Platform, Bangalore (BLR1)** (see
`docs/PRODUCTION_READINESS.md` Decision 0). Spec: [`.do/app.yaml`](../.do/app.yaml).

## One-time setup

1. **Managed Postgres** (BLR1). In the DB settings, set the **connection pool
   to `session` mode** — `transaction` mode reuses a backend connection
   mid-transaction and leaks `search_path` across tenants
   (`FAILURE_MODES.md §2`). Point the app at the pool host, not the DB host.
2. **Managed Redis** (BLR1) — used for cache + Celery broker.
3. Create a non-superuser DB role for the app with `CREATE` on the database
   (django-tenants needs it for `auto_create_schema`) but not `SUPERUSER`.
4. `doctl apps create --spec .do/app.yaml`
5. Set secrets in the App Platform UI: `DJANGO_SECRET_KEY` (50+ random chars),
   `SENTRY_DSN`.
6. First superadmin:
   ```
   doctl apps run <app-id> --component web -- python manage.py createsuperuser
   doctl apps run <app-id> --component web -- python manage.py addstatictoken -t <email>
   ```
   Log in at `https://eraj.com/superadmin/` with a backup code, add a TOTP
   device, then remove the static tokens.

## Deploys

`deploy_on_push: true` on `main`. Each deploy runs the **`migrate` PRE_DEPLOY
job** before new containers go live:

```
python manage.py migrate_schemas --shared
python manage.py migrate_schemas --executor=multiprocessing
```

At 500+ schemas the second command dominates deploy time. Migration rules:

- **Additive first.** Add nullable columns / new tables, deploy, backfill,
  switch reads, drop the old shape in a *later* release. Never a
  column rename + code change in one deploy.
- A migration that fails on schema N leaves schemas 1..N-1 migrated. Re-running
  is safe (idempotent) but check the job logs for which schema broke.

## Processes

| Process | Count | Notes |
|---|---|---|
| `web` (gunicorn) | 2+ | autoscales on CPU; `/health/ready` gates rollout |
| `celery-worker` | 1+ | scale with queue depth |
| `celery-beat` | **exactly 1** | two schedulers = every periodic task fires twice |

## Rollback

App Platform keeps prior deployments — roll back in the UI. If a migration
already applied, roll back **code** but leave the (additive) schema; that's why
migrations must be backward-compatible with the previous release.
