# Eraj — Architecture

## Decision: schema-per-tenant (not shared-schema + tenant_id)

Every client (college) gets its own Postgres **schema** (`abc`, `xyz`, ...),
created and migrated automatically via [`django-tenants`](https://django-tenants.readthedocs.io/).
`SHARED_APPS` (auth, core: Client/Plan/Subscription, superadmin) live in the
`public` schema. `TENANT_APPS` (library, hostel, attendance, ...) are
migrated fresh into every tenant schema.

**Why this over shared-schema-with-`tenant_id`:** with schema-per-tenant, a
missing tenant filter in a query is structurally impossible to leak data —
the query literally cannot see another schema's table. With shared-schema,
one missed `WHERE tenant_id = ?` anywhere across 9 modules is a real
cross-client data leak, and Django's ORM does not enforce this by default.
Verified in `apps/library/tests/test_tenant_isolation.py` against a real
Postgres instance — see that file's docstring for what it actually proves.

**Trade-off accepted:** migrations run per-schema (`migrate_schemas` loops
over every tenant). At the likely scale here (dozens to low hundreds of
institutions, not millions of consumer signups) this is a non-issue. Revisit
if tenant count crosses ~1,000.

## Request flow

Tenant owns the domain; product is a URL path under it — **not** one domain
per product. `abc.eraj.com/api/library/...` and `abc.eraj.com/api/hostel/...`
are the same tenant, same schema, different path prefixes. See
`docs/REQUIREMENTS_GAP_ANALYSIS.md` "Finding 1" for why this was chosen over
a product-per-domain model (`library.eraj.com`, `abc.library.eraj.com`, ...).

```
Browser → abc.eraj.com/api/library/books/
  → TenantMainMiddleware (django-tenants)
      resolves Domain -> Client, sets Postgres search_path to `abc`
  → SubscriptionEnforcementMiddleware (apps/core/middleware.py)
      reads cached {status, active_modules} for this tenant (Redis)
      402 if status is suspended/terminated
      403 if the requested path's module isn't in the plan
        (MODULE_PATH_PREFIXES maps "/api/library" -> "library", etc.)
  → DRF view executes, naturally scoped to the `abc` schema
```

## Core (public-schema) models

- `Client` (TenantMixin) — one row per tenant; owns a Postgres schema.
- `Domain` (DomainMixin) — hostname → Client mapping.
- `Plan` — named bundle, e.g. "Standard".
- `Module` — a product/module, e.g. "library". Data-driven so Super Admin
  can toggle without a deploy.
- `PlanModule` — pivot: which modules a plan includes.
- `Subscription` — **the single source of truth for access.** Explicit
  state machine (`active → grace_period → suspended → terminated`), not
  inferred ad-hoc from `end_date` at each call site. See
  `Subscription.recompute_status()` and `docs/FAILURE_MODES.md`.

## Enforcement is cached, not re-derived per request

`apps/core/middleware.get_subscription_state()` caches
`{status, modules}` per tenant in Redis
(`MODULE_PERMISSION_CACHE_TTL`, default 180s). Invalidated explicitly on
`Subscription` save via `apps/core/signals.py` — the TTL is a backstop for
cases the signal doesn't cover, not the primary invalidation path.

Deliberately does **not** bake module access into a long-lived JWT claim:
a plan downgrade must take effect within the cache TTL, not at next login.
Access tokens are short-lived (15 min) for the same reason — see
`SIMPLE_JWT` in `config/settings.py`.

## Background jobs (Celery)

Every tenant-scoped task takes `schema_name` as an **explicit** argument
(`apps/core/tasks.generate_fees_report`). Nothing relies on request
thread-local tenant context surviving into a worker process — it doesn't,
since workers pick tasks off a broker queue independently of any request.

`recompute_all_subscription_statuses` runs daily (Celery beat), walks every
`Subscription`, applies the deterministic transition function, and
invalidates the Redis cache for anything that changed.

## Frontend (Next.js)

One Next.js app, not one per product. `middleware.ts` reads the *tenant*
subdomain from the `Host` header and sets `x-tenant-slug`; each product is a
plain route under `app/` (`app/library/`, `app/hostel/`, ...), not a
subdomain-keyed route group. JWT auth via `httpOnly` cookie
(`frontend/lib/auth.ts`); see `frontend/README.md`.

## What's intentionally out of scope

- Dedicated Super Admin UI beyond the Django admin at `/superadmin/` (MFA-gated,
  core models registered) — see `docs/REQUIREMENTS_GAP_ANALYSIS.md` §7.
- Billing/payment provider integration.
- Product-per-domain routing (see "Request flow" above and
  `docs/REQUIREMENTS_GAP_ANALYSIS.md` Finding 1).
- Wildcard SSL / DNS automation for new tenant subdomains.
