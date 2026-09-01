# Eraj Frontend

One Next.js app serving every tenant and every module — mirrors the
backend's "one codebase, many tenants, many modules" principle (see
`../docs/ARCHITECTURE.md`).

## How tenant resolution works

- `middleware.ts` reads the `Host` header on every request, extracts the
  subdomain (`abc.eraj.com` -> `abc`), and sets it as an `x-tenant-slug`
  request header.
- `lib/tenant.ts#getTenantSlug()` reads that header in any Server Component.
- `lib/tenant.ts#fetchFromBackend()` / `postToBackend()` call the tenant's
  Django backend, attach the caller's JWT, unwrap DRF pagination, and
  translate the "expected" states — 401 (not signed in), 402 (subscription
  inactive), 403 (module not licensed) — into explicit messages. 402/403
  aren't bugs, they're the plan/subscription model working as designed.

## Auth

The backend API requires a tenant-bound JWT. `/login` (a Server Component +
Server Action) posts to `POST /api/auth/login/` and stores the access token
in an `httpOnly` cookie (`lib/auth.ts`). Module pages redirect to `/login`
when the token is missing or rejected. `POST /logout` clears it.

ponytail: no refresh flow — the 15-minute access token expires and the user
signs in again. Add an `/auth/refresh` route handler when sessions need to
outlast it. Tokens never touch client JS or `localStorage`.

No client-supplied value is ever trusted for access control — module and
subscription enforcement stays server-side in Django
(`apps/core/middleware.py`, `apps/accounts/authentication.py`). This frontend
only reads what the backend already decided.

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

The Django backend (see repo root) must be running on `localhost:8000` with
the demo tenants seeded (`python manage.py seed_demo_tenants`). That command
prints a per-tenant staff login (`staff@abc.eraj.test` /
`staff@xyz.eraj.test`, password `eraj-demo-pass-123`) and seeds sample books
(both) and rooms (`xyz`).

Flow: sign in at `abc.localhost:3000/login` → `/library` shows `abc`'s books;
`/hostel` shows "not included in the current plan" (Basic = library only).
Sign in at `xyz.localhost:3000` → both modules render.

> Re-verify end-to-end after the auth + pagination changes — not yet re-run
> against live servers.

## What's here vs. what's not

Built: tenant resolution middleware, JWT sign-in/out, Library and Hostel
pages fetching real (paginated) backend data, explicit handling of the
401 / subscription / module gate responses.

Not built: token refresh, Super Admin UI, write UI for the module workflows
(issue/return, allocate/vacate — the API is there), the remaining modules
(Attendance, HR, Fees, Exam, Transport) — each follows the same page pattern
as `app/library/page.tsx`.
