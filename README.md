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
cp .env.example .env   # DJANGO_ENV=dev by default; edit DB/Redis creds if needed

# Postgres + Redis must be running and reachable per .env.
# Fastest way: docker compose up -d db redis

python manage.py migrate_schemas --shared   # public schema: core, auth, accounts, admin
python manage.py migrate_schemas            # tenant schemas: auth, accounts, library, hostel
python manage.py seed_demo_tenants          # 'abc' and 'xyz' tenant schemas + subscriptions
python manage.py runserver
```

Add `abc.localhost` and `xyz.localhost` to your hosts resolution (most OSes
resolve `*.localhost` to 127.0.0.1 automatically). `seed_demo_tenants` creates
a staff user per tenant — `staff@abc.eraj.test` / `staff@xyz.eraj.test`,
password `eraj-demo-pass-123`. The API requires a tenant-bound JWT:

```bash
TOKEN=$(curl -s -X POST http://abc.localhost:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"staff@abc.eraj.test","password":"eraj-demo-pass-123"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access"])')

curl -H "Authorization: Bearer $TOKEN" http://abc.localhost:8000/api/library/books/
#   -> {"count": 3, "results": [...]}   (paginated)
# the same $TOKEN against xyz.localhost -> 401 (schema-bound)
```

Full API surface: `http://abc.localhost:8000/api/docs/` (Swagger).

Superadmin (public schema) is the MFA-gated Django admin at
`/superadmin/` — see `docs/DEPLOY.md` for the first-superadmin bootstrap.

Each request hits a genuinely separate Postgres schema.

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
apps/accounts/     # per-schema auth (custom User, JWT)
apps/library/      # TENANT_APPS: Book/Member/Issue/Fine/Hold — full lending workflow
apps/hostel/       # TENANT_APPS: Room/Resident/Allocation/Waitlist/Maintenance
apps/attendance/   # TENANT_APPS: Student, daily marking, % summary
apps/hr/           # TENANT_APPS: Department, Employee (CRUD)
apps/payroll/      # TENANT_APPS: Payslip off apps.hr.Employee
apps/fees/         # TENANT_APPS: FeeStructure, Payment, receipts
apps/exam/         # TENANT_APPS: Student, Subject, ExamResult
apps/transport/    # TENANT_APPS: Route, Vehicle, capacity-checked assignment
apps/inventory/    # TENANT_APPS: Item/IssueRecord — Library's pattern, adapted
docs/               # ARCHITECTURE.md, MODULES.md, FAILURE_MODES.md, TESTING.md,
                    # REQUIREMENTS_GAP_ANALYSIS.md, PRODUCTION_READINESS.md
```

Onboard a new tenant in one step (Client + Domain + Subscription + owner
user, rolled back together on any failure):

```bash
python manage.py create_tenant --name "ABC College" --slug abc \
  --domain abc.eraj.com --plan Standard \
  --owner-email owner@abc.edu --owner-password change-me-now
```

## Frontend

See `frontend/README.md`. A working Next.js app that resolves tenant from
subdomain via middleware and renders real data from the Library and
Hostel modules, including the 402 (subscription inactive) / 403 (module
not licensed) states from the backend's access-control model.

## Production

`docs/PRODUCTION_READINESS.md` is the plan (7 phases) and its status.
Auth, security headers, Docker/gunicorn, CI, observability, backups and the
DPDP/runbook docs are in place; `docs/DEPLOY.md` covers the DigitalOcean
(BLR1) target and `.do/app.yaml`.

## Modules

All 9 products from `docs/REQUIREMENTS_GAP_ANALYSIS.md`'s source spec are
built. Library and Hostel are full workflow depth — lending (issue / return /
renew / fines / holds) and residence (allocate / vacate / waitlist /
maintenance). Attendance, HR, Payroll, Fees, Exam, Transport, Inventory are
lean tier — CRUD plus the one core action each needs (see `docs/MODULES.md`
for why, and each module's API). Every module: row-locked
inventory/capacity where it matters, pagination + filtering, 409 on a
business-rule conflict, and an OpenAPI schema at `/api/schema/`
(`/api/docs/` for Swagger UI).

## What's next (not built here)

- Superadmin CRUD is via the Django admin at `/superadmin/`; a dedicated
  API/UI is still open.
- Attendance, HR, Payroll, Fees, Exam, Transport modules — replicate the
  `apps/library` pattern (TENANT_APPS entry + models with no tenant FK,
  service layer for workflows, ViewSet + router) on the backend, and the
  `frontend/app/library` page pattern on the frontend.
- Billing/payment provider integration.
- Load + isolation test under a real connection pool (`docs/FAILURE_MODES.md` §2).
