# DevOps — eraj-v1

**Date:** 2026-10-25 · decided with owner

## Staging (target live by 2026-11-10, used for client testing from 2026-11-11)
- **Host:** one Linux VPS in India (DigitalOcean BLR1, Lightsail Mumbai or equivalent), 4 GB RAM /
  2 vCPU, Ubuntu LTS. Owner provisions by ~2026-11-03 and shares SSH access.
- **Domain:** owner's personal domain.
  | Hostname | Serves |
  |---|---|
  | `eraj.abhisheksingh.in` | landing page (no tenant) |
  | `<schema>.eraj.abhisheksingh.in` | one per client (e.g. `pqr.eraj.abhisheksingh.in`) |
  | `admin.eraj.abhisheksingh.in` | public-schema Django superadmin (MFA) |
- **DNS:** two A records → VPS IP: `eraj.abhisheksingh.in`, `*.eraj.abhisheksingh.in`.
- **TLS:** Caddy with on-demand TLS; an `ask` endpoint on Django returns 200 only for hostnames
  present in `core.Domain` (+ the apex/admin), so certificates are issued only for real tenants.
  No DNS-provider API key needed (no wildcard cert).
- **Compose services:** caddy, web (gunicorn), next (next start), worker (celery), beat (celery,
  exactly 1), postgres 16, redis 7. Only caddy publishes ports (80/443).
- **Django is not public.** Next talks to Django on the internal network
  (`ERAJ_BACKEND_ROOT=web:8000`, Host header set per tenant); Caddy routes only
  `admin.…` to Django directly.

## Code changes this requires (M7)
- `frontend/proxy.ts`: root hosts from env (`ERAJ_ROOT_DOMAIN`), not hard-coded `eraj.com`.
- `frontend/lib/backend.ts`: internal-network mode = set `Host: <tenant>.<root>` on `http` requests.
- Django: `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` for `.eraj.abhisheksingh.in`; `/internal/tls-ask`.
- `docker-compose.staging.yml`, `Caddyfile`, `.env.staging.example`, deploy runbook.

## Production
Unchanged from docs/PRODUCTION_READINESS.md (DO App Platform BLR1 + managed Postgres in session
pool mode) — revisit when the first contract is signed.
