# Eraj Frontend

One Next.js app serving every tenant and every module — mirrors the
backend's "one codebase, many tenants, many modules" principle (see
`../docs/ARCHITECTURE.md`).

## How tenant resolution works

- `middleware.ts` reads the `Host` header on every request, extracts the
  subdomain (`abc.eraj.com` -> `abc`), and sets it as an `x-tenant-slug`
  request header.
- `lib/tenant.ts#getTenantSlug()` reads that header in any Server Component.
- `lib/tenant.ts#fetchFromBackend()` calls the tenant's Django backend and
  translates the platform's two "expected" error states — 402 (subscription
  inactive) and 403 (module not licensed) — into explicit messages, since
  those aren't bugs, they're the plan/subscription model working as
  designed.

No client-supplied value is ever trusted for access control — module and
subscription enforcement stays server-side in Django
(`apps/core/middleware.py` in the backend repo). This frontend only reads
what the backend already decided.

## Local development

Django's dev server doesn't resolve `*.localhost` subdomains to itself
without `/etc/hosts` entries, so in local dev the tenant is passed via a
`Host` header override instead of being part of the URL — see
`backendRequest()` in `lib/tenant.ts`. In production, the tenant IS part of
the URL (`abc.eraj.com`) exactly as django-tenants expects.

```bash
npm install
cp .env.local.example .env.local
npm run dev
```

Visit `http://abc.localhost:3000` or `http://xyz.localhost:3000` in a
browser — most desktop OSes resolve `*.localhost` to 127.0.0.1
automatically. If your environment doesn't (some sandboxes/CI don't),
send a `Host: abc.localhost` header instead — this is exactly what
`lib/tenant.ts` does internally for its own backend calls, since Node's
`fetch()` forbids overriding the `Host` header itself:

```bash
curl -H "Host: abc.localhost:3000" http://127.0.0.1:3000/library
```

The Django backend (see repo root) must be running on `localhost:8000`
with the `abc`/`xyz` demo tenants seeded (`python manage.py seed_demo_tenants`).

**Verified working end-to-end** (both servers running locally): `abc` and
`xyz` each render their own Library data through the real page (not
mocked), and requesting `/hostel` as `abc` (Basic plan, library only)
correctly renders "This module is not included in the current plan."
instead of data — proving the 402/403 backend gate surfaces properly all
the way through the frontend.

## What's here vs. what's not

Built: tenant resolution middleware, Library and Hostel module pages
fetching real backend data, explicit handling of the subscription/module
gate responses.

Not built: Super Admin UI, auth/login flow, the remaining modules
(Attendance, HR, Fees, Exam, Transport) — each follows the same page
pattern as `app/library/page.tsx`.
