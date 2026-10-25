# QA — index

## [DISCOVERED] Verified 2026-10-25 against live Postgres 16 + Redis 7
- `migrate_schemas --shared` and tenant migrations: apply cleanly.
- `seed_demo_tenants`: creates abc/xyz/pqr schemas + subscriptions + staff users.
- Live HTTP: login on `abc` → token → `/api/library/books/` returns 3 books; same token on `xyz` → 401.
- `apps.library.tests.test_tenant_isolation`: 3/3 pass.
- `apps.accounts.tests`, `apps.core.tests`, `apps.hostel.tests` (Django runner): 8/8 pass.
- `pytest apps/core/tests/`: 23/23 pass.
- `check --deploy` (prod env): 0 security warnings; 33 drf-spectacular schema warnings
  (duplicate `Student` component names, unresolved auth extension).
- Frontend: `tsc --noEmit` clean; `next build` succeeds.
- FAIL: `makemigrations --check` → drift in `apps/fees`.

## Quality gate for 2026-11-11 staging
Every acceptance scenario in the scope doc runs on staging; each module has API tests for its
business rules; cross-tenant and cross-branch negative tests stay green.
