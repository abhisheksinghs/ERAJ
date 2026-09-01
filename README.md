# Eraj — Multi-Product SaaS Platform

One Django codebase → multiple product modules → multiple client tenants →
different plans, with schema-per-tenant isolation on Postgres. Includes a
working Next.js frontend that consumes the real backend API.

See `docs/ARCHITECTURE.md` for the design and why schema-per-tenant was
chosen over shared-schema+`tenant_id`, and `docs/FAILURE_MODES.md` for the
risk catalog (including two real issues this build actually hit and fixed).

## Stack

Django 5 + `django-tenants` (schema-per-tenant on Postgres) + Django REST
Framework + `djangorestframework-simplejwt` + Celery + Redis. Frontend
(Next.js) is not part of this skeleton — see the "Next.js" note in
`docs/ARCHITECTURE.md` for the intended routing pattern.

## Local setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit DB/Redis credentials if needed

# Postgres + Redis must be running and reachable per .env.
# Fastest way: docker compose up -d db redis

python manage.py migrate_schemas --shared   # public schema: core, auth, admin
python manage.py seed_demo_tenants          # creates 'abc' and 'xyz' tenant schemas + subscriptions
python manage.py runserver
```

Add `abc.localhost` and `xyz.localhost` to your hosts resolution (most OSes
resolve `*.localhost` to 127.0.0.1 automatically). Then:

```bash
curl http://abc.localhost:8000/api/library/books/
curl http://xyz.localhost:8000/api/library/books/
```

Each hits a genuinely separate Postgres schema.

## Docker

```bash
docker compose up --build
```

Brings up Postgres, Redis, the Django app, a Celery worker, and Celery beat.

## Tests

```bash
python manage.py test apps.library.tests.test_tenant_isolation -v 2   # real-schema isolation proof
python -m pytest apps/core/tests/ -v                                   # fast unit tests
```

See `docs/TESTING.md` for what's covered by which suite and what's
deliberately not covered yet.

## Project layout

```
config/            # settings, URLconfs (public vs tenant), Celery app
apps/core/         # SHARED_APPS: Client, Domain, Plan, Module, Subscription,
                    # subscription-enforcement middleware, Celery tasks
apps/library/      # TENANT_APPS example module (Book, Member, Issue)
apps/hostel/       # TENANT_APPS example module (Room, Resident) — minimal,
                    # exists to prove the pattern generalizes beyond one module
docs/               # ARCHITECTURE.md, FAILURE_MODES.md, TESTING.md
```

## Frontend

See `frontend/README.md`. A working Next.js app that resolves tenant from
subdomain via middleware and renders real data from the Library and
Hostel modules, including the 402 (subscription inactive) / 403 (module
not licensed) states from the backend's access-control model.

## What's next (not built here)

- Superadmin panel (client/plan/subscription CRUD UI) — the data model
  exists (`Client`, `Plan`, `Module`, `PlanModule`, `Subscription`); only
  the UI/API views are missing.
- Attendance, HR, Payroll, Fees, Exam, Transport modules — replicate the
  `apps/library` pattern (TENANT_APPS entry + models with no tenant FK,
  isolation comes from the schema) on the backend, and the
  `frontend/app/library` page pattern on the frontend.
- Billing/payment provider integration.
- pgbouncer load-testing (see `docs/FAILURE_MODES.md` §2).
