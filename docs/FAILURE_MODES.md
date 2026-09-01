# Eraj — Failure Modes

This catalog was written before any code existed, then updated as building
and testing this skeleton surfaced real instances. Entries marked
**[confirmed]** were actually hit and fixed while writing this codebase, not
theoretical.

## 1. Tenant resolution

| Failure mode | Guard implemented here |
|---|---|
| Stale tenant cache after suspend/delete | `apps/core/signals.py` invalidates on every `Subscription.save()`; TTL (180s) is a backstop only |
| Missing tenant falling back to `public` schema | Not configured — `SHOW_PUBLIC_IF_NO_TENANT_FOUND` is left unset, so `TenantMainMiddleware` raises `Http404` on an unresolved hostname rather than silently serving public-schema data |
| Subdomain collision / bad slugs | `Client.slug` is a `SlugField(unique=True)`; enforce normalization at tenant-creation time in the (not-yet-built) Superadmin UI |

## 2. Data isolation — **[confirmed]**

`search_path`/connection-pooling correctness was the #1 theoretical risk
flagged before any code was written. It's covered by
`apps/library/tests/test_tenant_isolation.py`, run against a real Postgres
16 instance (not mocked):

- `test_book_created_in_one_tenant_is_invisible_in_another` — direct ORM
  proof via `tenant_context()`.
- `test_same_isbn_allowed_across_tenants` — proves isolation is at the
  table level (identical unique constraint, different physical tables),
  not an application-level filter.
- `test_http_request_resolves_correct_tenant_schema` — same proof, but
  through the actual HTTP path (`TenantMainMiddleware` +
  `SubscriptionEnforcementMiddleware`), because ORM-level correctness
  doesn't guarantee middleware-level correctness.

**Not yet tested here:** pgbouncer in transaction-pooling mode. This
skeleton runs with `CONN_MAX_AGE=0` (a fresh connection per request), which
sidesteps the risk but doesn't scale-test it. If you introduce pgbouncer,
either use session-pooling mode (search_path survives per-session safely)
or add an explicit test that opens N concurrent requests across M tenants
against a pooled connection and asserts no cross-tenant read occurs.

## 3. Descriptor-level caching — **[confirmed, found while testing]**

Not in the original pre-build catalog. `apps/core/middleware.py` originally
read `client.subscription` (Django's reverse one-to-one accessor). That
accessor caches its result **on the Python `client` object itself**,
independent of the Redis cache layer built to solve the "stale permission"
problem. A long-lived `client`/tenant instance (e.g. reused across a Celery
task and a later call in the same process) could return stale subscription
data even after the Redis cache was correctly invalidated.

Caught by `test_recompute_invalidates_stale_cache` in
`apps/core/tests/test_tasks.py`, which failed on the first run. Fixed by
querying `Subscription.objects.get(client=client)` explicitly instead of
the cached accessor. **Lesson generalized:** any "cache invalidation" story
needs to account for ORM-level object caching, not just your explicit cache
layer (Redis/memcached) — they're two different caches with different
invalidation rules.

## 4. Subscription / billing enforcement

| Failure mode | Guard implemented here |
|---|---|
| Race condition on expiry mid-session | `SIMPLE_JWT.ACCESS_TOKEN_LIFETIME = 15 minutes`; module access is re-checked (cache-backed) on every request, not baked into the token |
| Partial module downgrade not enforced | `MODULE_PERMISSION_CACHE_TTL` (180s default) bounds staleness; `apps/core/signals.py` invalidates immediately on save |
| Grace period ambiguity | `Subscription.recompute_status()` is the single deterministic transition function — all enforcement reads `status`, never re-derives it from `end_date` ad hoc. Unit-tested exhaustively at the day-boundary in `test_subscription_state_machine.py` (day-of-expiry, day-after, last-grace-day, first-suspended-day, zero-grace-period) |

## 5. Background jobs (Celery)

| Failure mode | Guard implemented here |
|---|---|
| Task loses tenant context | Every tenant-scoped task takes `schema_name` as an explicit argument (`apps/core/tasks.generate_fees_report`); nothing relies on thread-local context |
| Tenant deleted mid-task | `generate_fees_report` re-fetches `Client.objects.get(schema_name=...)` inside `schema_context()` before doing anything — fails fast if the tenant is gone, rather than writing orphaned data |

## 6. Migrations

| Failure mode | Notes |
|---|---|
| Partial migration across schemas | `migrate_schemas` is NOT wrapped in cross-schema rollback here — if it fails on tenant N of M, tenants 1..N-1 are on the new schema and N+1..M are not. **Not solved in this skeleton** — needs a CI/CD step that monitors `migrate_schemas` exit codes per-tenant and alerts on partial failure. Treat as a known gap, not a false sense of safety. |
| New TENANT_APPS model added without backfill plan | Sequence migrations before module-permission rollout: run `migrate_schemas` first, only then flip the `PlanModule`/`Module` toggle. Not automated here. |

## 7. Frontend (Next.js) — not built in this skeleton

Documented for the next phase: subdomain-parsing middleware needs an
explicit fallback for `localhost`/preview-deployment hosts that don't have
a parseable subdomain, and cached tenant/module state in React
Query/SWR needs a short stale time or explicit invalidation on
subscription-changed events — otherwise a client can see UI for a module
they just lost access to and get a 403 on click.

## Priority order (unchanged from the pre-build review, now with evidence)

1. `search_path` / connection-pooling correctness — **tested, passing**
2. Tenant resolution fallback behavior — **configured, not load-tested**
3. Subscription state machine — **tested exhaustively at boundaries**
4. Celery explicit tenant context — **implemented, unit-tested for the daily recompute task**
5. Migration sequencing discipline — **documented gap, not automated**
6. Frontend cache invalidation — **not yet built**
