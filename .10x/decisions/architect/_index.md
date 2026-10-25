# Architect — index

## [DISCOVERED] Current architecture (2026-10-25)
- Django 5 monolith + DRF + SimpleJWT, `django-tenants` schema-per-tenant on Postgres 16.
- `TENANT_MODEL = core.Client`; tenant resolved by subdomain (`abc.eraj.com`); module chosen by
  URL path (`/api/<module>/…`), licensed via `core.Plan/Module/Subscription`, enforced in
  `SubscriptionEnforcementMiddleware` (402 inactive, 403 unlicensed).
- Users are per-schema (`auth` + `accounts` in TENANT_APPS); tokens carry a `schema` claim and
  `TenantBoundJWTAuthentication` rejects mismatches (verified live: cross-tenant → 401).
- Superadmins live in `public`, MFA-gated admin at `/superadmin/`.
- Celery + Redis for async; Redis holds no authoritative data.
- Modules are independent apps; each keeps its own person record (Library `Member`, Hostel
  `Resident`, Attendance/Exam `Student`, Transport freetext riders). No shared registry.
- Next.js 14 App Router frontend with a BFF Route Handler holding JWTs in httpOnly cookies;
  pages exist only for login/logout/home/library/hostel (read-only lists).

## Active features
| Slug | File | State |
|---|---|---|
| eraj-v1 | eraj-v1.md | Design approved 2026-10-25 (ADR-001–006) |
