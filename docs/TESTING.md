# Eraj — Testing Strategy

Two test runners, deliberately split by what they're good at:

## `manage.py test` — real tenant-schema integration tests

`django-tenants` ships `TenantTestCase`, which creates an actual Postgres
schema per test class and lets you switch between real schemas mid-test via
`tenant_context()`/`schema_context()`. This is the ONLY way to genuinely
test cross-schema isolation — pytest-django's default transaction-per-test
model doesn't manage multiple schemas.

```bash
python manage.py test apps.library.tests.test_tenant_isolation -v 2
```

Location: `apps/<tenant_app>/tests/test_*isolation*.py`. These are slower
(real schema creation) — keep them focused on genuinely cross-schema
concerns, not general business logic.

## `pytest` — fast unit tests

Everything that doesn't need multiple real schemas: the `Subscription`
state machine (pure function of dates), middleware request-routing logic
(stub a `Client` + `Subscription` in the single default test schema),
Celery task logic. Uses `pytest-django`'s `db`/`django_db` fixtures.

```bash
python -m pytest apps/core/tests/ -v
```

Config: `pytest.ini` points `DJANGO_SETTINGS_MODULE` at
`config.settings_test`.

## What each suite currently covers

| Area | Suite | File |
|---|---|---|
| Cross-tenant data isolation (ORM level) | `manage.py test` | `apps/library/tests/test_tenant_isolation.py` |
| Cross-tenant isolation (HTTP/middleware level) | `manage.py test` | same file |
| Unique constraints don't collide across schemas | `manage.py test` | same file |
| Subscription state machine (all day-boundary cases) | `pytest` | `apps/core/tests/test_subscription_state_machine.py` |
| Middleware: block/allow by status and module | `pytest` | `apps/core/tests/test_middleware.py` |
| Cache invalidation on downgrade | `pytest` | `apps/core/tests/test_middleware.py`, `test_tasks.py` |
| Daily subscription recompute task | `pytest` | `apps/core/tests/test_tasks.py` |

## Deliberately not covered yet

- pgbouncer / connection-pooling behavior under concurrent load (see
  `docs/FAILURE_MODES.md` §2) — needs a load-testing setup, not a unit test.
- Migration partial-failure handling across many schemas.
- Frontend (Next.js) subdomain-routing middleware — no frontend code exists
  in this skeleton yet.
- Superadmin cross-tenant reporting views — not built yet.

## Running everything

```bash
# 1. Real-schema integration tests
python manage.py test apps.library.tests.test_tenant_isolation -v 2

# 2. Fast unit tests
python -m pytest apps/core/tests/ -v
```

Both require a running Postgres (`DB_HOST`/`DB_PORT` etc. from `.env`) and
Redis (`REDIS_URL`) — see `docker-compose.yml` for one-command local setup.
