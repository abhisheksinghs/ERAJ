# DevOps — index

## [DISCOVERED] Current delivery setup (2026-10-25)
- `Dockerfile`: multi-stage, non-root, collectstatic at build, gunicorn CMD.
- `docker-compose.yml`: dev only (Postgres, Redis, app, Celery worker, beat).
- `.github/workflows/ci.yml`: tests + `check --deploy` + `makemigrations --check` + frontend `tsc`/build; scanners informational.
- `.do/app.yaml`: DO App Platform spec (web, worker, beat) for BLR1; managed Postgres pool must be `session` mode.
- No staging environment exists yet.

## Open
- Staging host for 2026-11-11 (status.md B2).
- Python 3.13 runtime needs `psycopg2-binary>=2.9.10`.
