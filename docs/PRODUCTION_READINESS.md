# Eraj — Production-Readiness & Security Plan

Target (decided): **real SaaS, first paying customers** — Indian institutions
storing real student data. Design headroom: **500+ tenants / spiky traffic**.
Auth model (decided): **users isolated per tenant schema**.

Those last two pull against each other ("ship for the first customer" vs
"design for 500+"). Resolution used throughout this plan: **build Phases 1–2
and 4–7 fully before launch; build Phase 3 to the point where the design is
locked and the pooler is configured correctly, defer the fan-out tooling
until schema count crosses ~100; Phase 6 baseline now, formal program later.**

Feature completeness (remaining modules, billing integration) is tracked
separately — this document is only about making what exists safe to run for
money. The Library and Hostel modules are now built out to full workflow depth
(see `docs/MODULES.md`); Attendance/HR/Fees/Exam/Transport still follow that
pattern.

---

## Decision 0 — Hosting

**Recommendation: DigitalOcean, Bangalore (BLR1) region.**

- **App Platform** for `web`, `celery_worker`, `celery_beat` (three components,
  one repo). Gives TLS, HTTP/2, CPU-based autoscaling, zero-downtime deploys,
  a secret store, and log/metric drains with no ops work.
- **Managed Postgres** (BLR1). Its built-in connection pool **must be set to
  `session` mode** — see Phase 3; `transaction` mode silently breaks
  `search_path` and is the #1 django-tenants production incident.
- **Managed Redis** (BLR1) — cache + Celery broker. Nothing authoritative
  lives here, so no backup needed.

Why not the alternatives:

| Option | Verdict |
|---|---|
| Single VM + Compose | Too fragile for paid customers: no rollback, manual TLS, one box = one outage. Fine for `staging` only. |
| Render / Railway / Fly | Lower-friction than DO in places, but **no India region** at time of writing → fails DPDP data-localization expectations. Verify current region lists before committing. |
| Kubernetes / ECS | Real answer *if* you outgrow App Platform's autoscaler (spiky to very large, or >~20 app instances). Not before — it's a platform-team's worth of YAGNI today. |

**Scale path:** when App Platform's autoscaler is the bottleneck, move the
three containers to **AWS `ap-south-1` ECS Fargate + RDS Postgres +
ElastiCache** (target-tracking autoscaling, PITR, IAM). The database is the
anchor; containers are disposable. Plan the DB on a provider you're willing to
stay on (RDS Mumbai is the safe long-term bet).

**Environments:** `dev` (local compose), `staging` (DO, seeded fake tenants),
`prod` (DO, BLR1). Separate databases, separate secret sets, no shared
credentials.

---

## Phase 1 — Authentication & authorization  *(largest gap; nothing exists today)*

Current state: `SIMPLE_JWT` is configured but there are **no login/refresh
endpoints**, `apps.library.BookListView` is `AllowAny`, `RoomListView`
inherits `IsAuthenticated` (so it 401s forever). No user model beyond stock
`auth.User` in `SHARED_APPS`.

1. **Custom user model now** (cannot be added later without a painful
   migration). New `apps/accounts` app, `AbstractUser` subclass, `email` as
   `USERNAME_FIELD`. Set `AUTH_USER_MODEL` before the first real migration.
2. **Per-schema users.** Put `django.contrib.auth` + `apps.accounts` in
   `TENANT_APPS` (keep `auth` in `SHARED_APPS` too — public-schema users are
   the superadmins). Each tenant schema gets its own `accounts_user` table.
   Document this in `ARCHITECTURE.md`.
3. **Auth endpoints** — use `djangorestframework-simplejwt` views, write no
   auth logic:
   - `TokenObtainPairView` / `TokenRefreshView`
   - logout via `rest_framework_simplejwt.token_blacklist` (add the app, run
     its migrations into every schema)
   - password reset via `django.contrib.auth` reset views (email link) — one
     transactional email template.
4. **Schema-bound tokens — security-critical, ~15 lines.** Because auth is
   per-schema, a token minted for tenant `abc` will authenticate against
   tenant `xyz`'s `accounts_user` table by primary-key collision if `xyz` is
   ever resolved for that request. Mitigation:
   - add a `schema` claim at mint time (subclass `TokenObtainPairSerializer`),
   - a `TenantBoundJWTAuthentication(JWTAuthentication)` that rejects any token
     whose `schema` claim ≠ `request.tenant.schema_name`,
   - set it as the only `DEFAULT_AUTHENTICATION_CLASSES` entry,
   - **negative test**: mint in `abc`, call `xyz` endpoint, assert 401.
5. **RBAC.** Roles per tenant: `owner` / `staff` / `read_only` (a `role` field
   on the user, or Django groups seeded per schema). One DRF permission class
   per write-capability; module-level access stays with the existing
   `SubscriptionEnforcementMiddleware`. **Delete every `AllowAny`.** Add
   `permission_classes` explicitly on every view — no reliance on defaults.
6. **Brute-force / credential stuffing.** DRF `ScopedRateThrottle` on the
   login scope (e.g. `5/min` per IP) now; a WAF (Cloudflare in front of DO)
   later. `django-axes` if you want lockouts without a WAF.
7. **MFA (TOTP)** via `django-otp` + `django-otp`'s `TOTPDevice`: **required**
   for all public-schema superadmins, **offered** to tenant `owner` accounts.
   This is non-negotiable for "security proofed" given superadmin can touch
   every tenant.
8. **Frontend token handling.** Tokens go in `httpOnly; Secure; SameSite=Lax`
   cookies set by a Next.js Route Handler acting as a thin BFF — **never
   `localStorage`**. Server Components read the cookie and attach `Bearer` to
   backend calls. Refresh handled server-side.

---

## Phase 2 — Transport, headers, config hardening  *(mostly settings)*

1. **Split settings** or env-gate: `DEBUG` must be `False` in prod and a
   startup assertion should fail if `DEBUG and not DEV`. Today `settings.py`
   defaults `DEBUG=False` (good) but reads it from `.env`.
2. **`manage.py check --deploy` clean**, enforced in CI. It will flag most of
   the following:
   - `SECURE_SSL_REDIRECT = True`
   - `SECURE_HSTS_SECONDS = 31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`,
     `SECURE_HSTS_PRELOAD = True`
   - `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`
   - `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` (DO
     terminates TLS at the router)
   - `SECURE_CONTENT_TYPE_NOSNIFF = True`, `X_FRAME_OPTIONS = "DENY"`
3. **`ALLOWED_HOSTS`** = `.eraj.com` (wildcard for tenant subdomains) + apex.
   `TenantMainMiddleware` already 404s unknown subdomains via the `Domain`
   table — keep that as the real allowlist; `ALLOWED_HOSTS` is the outer
   guard. Add a test that an unknown subdomain 404s (not 500s).
4. **CORS** — `django-cors-headers` (one dep), `CORS_ALLOWED_ORIGIN_REGEXES =
   [r"^https://[a-z0-9-]+\.eraj\.com$"]`. `CSRF_TRUSTED_ORIGINS` likewise.
5. **CSP** — `django-csp` on the Django side (mainly protects `/admin`);
   frontend CSP + `Referrer-Policy`, `Permissions-Policy`, `X-Content-Type-
   Options` via `next.config.js` `headers()`.
6. **Django admin lockdown.**
   - Remove `admin/` from `config/urls.py` (the **tenant** URLconf) — tenant
     staff use the API, not Django admin. Keep it only in
     `config/urls_public.py`.
   - Move it off `/admin/` to an unguessable path.
   - Put it behind MFA (Phase 1.7) and, ideally, an IP allowlist or the WAF.
7. **`.env.example`** — make the placeholder secret obviously fake
   (`REPLACE_ME`), document that prod values come from the platform secret
   store, never a file.

---

## Phase 3 — Multi-tenant data layer at 500+ schemas

1. **Connection pooling (do this before launch).** Set the managed-Postgres
   pool to **`session` mode**. `transaction` mode reuses a backend connection
   mid-transaction across clients, so a `SET search_path` from tenant A can
   leak into tenant B's query — exactly `FAILURE_MODES.md §2`, which is
   currently *tested at the ORM level but never under a real pool*.
   - Keep `CONN_MAX_AGE = 0`.
   - Add an integration test: acquire a pooled connection, switch tenant,
     assert `SHOW search_path` reflects the switch and never a stale value.
   - Document "pool mode = session" as load-bearing config in
     `ARCHITECTURE.md` and the deploy runbook.
2. **Least-privilege DB roles.** App connects as a non-superuser role with
   `CREATE` on the DB (needed for `auto_create_schema`) but not `SUPERUSER`.
   Today `DB_USER=postgres`. A separate migration role can own schemas if you
   want to drop `CREATE` from the runtime role and create schemas out-of-band.
3. **Migration fan-out** (build when schema count > ~100, design now):
   - `migrate_schemas --executor=multiprocessing` as a **pre-deploy job**
     (App Platform pre-deploy command), never on web-container start.
   - Time budget + per-schema pass/fail report + resume-from-failure.
   - Zero-downtime discipline: additive migration → deploy code that tolerates
     both shapes → backfill → switch reads → drop old column in a later
     release. Write this as a checklist in `docs/`.
4. **Tenant lifecycle as one transactional operation:**
   - onboarding: `Client` + `Domain` + `Subscription` + schema + role seed +
     owner user, all-or-nothing, with rollback (schema drop) on any failure.
   - offboarding: export (`pg_dump -n <schema>`) → verify → `drop_schema`.
     Right-to-erasure is genuinely clean here — note it for DPDP (Phase 6).
5. **Fix the state machine bugs** (`apps/core/models.py`):
   - `recompute_status()` can return `ACTIVE`/`GRACE_PERIOD`/`SUSPENDED` but
     **never `TERMINATED`** — the enum branch is dead. Decide the transition
     (manual by superadmin, or auto after N days suspended) and implement it.
   - `active_modules()` returns the plan's modules regardless of status;
     callers must remember to also check `is_access_allowed()`. Add
     `granted_modules()` that returns `[]` unless access is allowed, and route
     the middleware through it so the safe path is the default path.
6. **Cache stampede.** On invalidation, N concurrent requests all miss and hit
   Postgres. Low severity at launch RPS — add jittered TTL
   (`ttl ± random(0, ttl*0.1)`) when it shows up in metrics.
   `# ponytail: plain TTL now, jitter/lock when p99 shows stampede`.

---

## Phase 4 — Runtime & deployment

1. **Real app server.** `gunicorn config.wsgi:application` (sync workers,
   `workers = 2*cpu + 1`, `--timeout 30`, `--max-requests 1000
   --max-requests-jitter 100`). Drop `runserver` from every non-dev path
   (it's in `docker-compose.yml` today).
2. **Dockerfile** (`Dockerfile` today runs as root, ships `gcc`, no
   `collectstatic`, no `.dockerignore`):
   - multi-stage: build wheels in stage 1, copy into a slim runtime stage
   - non-root `USER app`
   - `psycopg[binary]` or prebuilt wheels → no `gcc`/`libpq-dev` in the final
     image
   - pin the base image by digest
   - `RUN python manage.py collectstatic --noinput` at build
   - add `.dockerignore` (`.git`, `frontend/node_modules`, `*.pyc`, `.env`, …)
   - keep a separate `docker-compose.dev.yml` with the source bind-mount; the
     prod image has code baked in, no volume.
3. **Static / media.** `whitenoise` for static (one dep, no CDN needed at
   launch). Media (future file uploads for fees/exam/etc.) → S3-compatible
   (DO Spaces, BLR1) with **per-tenant key prefixes** and signed URLs; build
   this only when the first module needs uploads.
4. **Healthchecks.** Keep `/health` as liveness. Add `/health/ready` that
   checks a DB round-trip + Redis `PING`; wire it to App Platform's health
   check so a broken dependency stops the rollout.
5. **Celery hardening** (`config/celery.py`):
   - `task_time_limit` / `task_soft_time_limit`
   - `task_acks_late = True`, `task_reject_on_worker_lost = True`
   - `worker_max_tasks_per_child = 100` (guard against slow leaks)
   - result backend TTL (`result_expires`)
   - `beat` runs as **exactly one** instance (App Platform component with
     `instance_count: 1`, no autoscale)
   - separate queues: platform tasks (`recompute_all_subscription_statuses`)
     vs tenant-scoped tasks
   - every tenant-scoped task takes `schema_name` explicitly and enters
     `schema_context` — the codebase already does this; add a lint/review rule
     so it stays true.
6. **CI/CD** (GitHub Actions):
   - `ruff` (lint+format), `bandit` (SAST), `pip-audit` (deps), `gitleaks`
     (secrets), `python manage.py check --deploy`
   - both test suites against `postgres:16` + `redis:7` service containers
   - frontend: `tsc --noEmit`, `next build`, `npm audit --audit-level=high`
   - build image → deploy `staging` on merge to `main` → deploy `prod` on tag
   - `migrate_schemas` runs as the pre-deploy step, gated on staging success.

---

## Phase 5 — Observability, backups, incident readiness

1. **Error tracking.** Sentry (backend + frontend). `send_default_pii=False`,
   scrub `email`/`phone`/`Authorization` in a `before_send` hook, tag every
   event with `schema_name`, enable release tracking.
2. **Structured logging.** JSON logs via stdlib `logging` config (no new dep
   needed) or `structlog`. **Every line carries `schema_name` + request id.**
   No PII in log messages — scrub or omit. Ship to App Platform's log drain →
   a searchable store (Loki / Better Stack / Datadog — cheapest that meets
   retention).
3. **Metrics.** `django-prometheus` (one dep): request latency histogram, DB
   connection count, per-tenant request counters, Celery queue depth + task
   latency. Dashboard + alerts on p99 latency, 5xx rate, queue backlog, DB
   connections near the pool ceiling.
4. **Audit trail.** Append-only `AuditLog` model in the **public** schema:
   auth events (login, failure, MFA, password reset), subscription/plan
   changes, every superadmin action, and any cross-tenant access. Populate via
   signals + a small middleware. Retention ≥ 1 year.
5. **Backups.**
   - Managed Postgres **PITR** enabled, 14–30 day window.
   - **Monthly restore drill**, actually executed: restore to a scratch DB,
     verify row counts, verify a single-tenant extract (`pg_dump -n <schema>`)
     round-trips. A backup you have never restored is not a backup.
   - Redis: cache only → no backup. Add an assertion/review note that nothing
     authoritative is ever written to Redis.
6. **Incident runbook** (`docs/INCIDENT_RUNBOOK.md`): on-call contact, severity
   ladder, first-response steps per failure mode (extend the existing
   `FAILURE_MODES.md`), rollback procedure, and the **DPDP breach path**:
   assess → notify the Data Protection Board of India and affected principals
   **without undue delay** → post-mortem. Comms templates pre-written.

---

## Phase 6 — DPDP & data governance  *(Indian student data)*

1. **Data map.** Per module: what PII is stored (names, emails, phone,
   possibly minors' data → heightened care), which schema, retention period,
   lawful basis.
2. **Contracts.** A Data Processing Agreement template for institutions (you
   are the processor, the institution is the fiduciary). Sub-processor list
   (DO, Sentry, email provider, log store) with a DPA signed with each.
3. **Consent & purpose limitation** captured at tenant onboarding.
4. **Retention & erasure.**
   - Tenant deletion = schema drop (clean, Phase 3.4).
   - Per-student erasure within a live tenant = a documented, tested procedure
     (soft-delete + purge job, or direct delete with FK `PROTECT` handling).
5. **Data localization.** All infra in an India region (Decision 0). Don't add
   a sub-processor that moves PII out of India without a DPA that permits it.
6. **Team access to prod.** Least-privilege, MFA-gated, break-glass account
   for emergencies, all prod DB access logged. Quarterly access review.

---

## Phase 7 — Security verification  *(gate for onboarding the first paying tenant)*

1. **Negative security test suite** (new `tests/security/`):
   - cross-tenant token reuse (Phase 1.4) → 401
   - IDOR: every detail/update/delete endpoint, authenticated as tenant A,
     targeting tenant B's object id → 404/403
   - privilege escalation: `staff` performing `owner`-only actions → 403
   - injection: malicious subdomain, malicious query/path params, malicious
     JSON bodies → no 500, no schema leak
   - JWT tampering: altered signature, `alg=none`, expired, wrong `schema`
     claim → 401
   - rate-limit actually triggers on the login scope
2. **`manage.py check --deploy`** → zero warnings, in CI.
3. **OWASP ZAP baseline** (passive) in CI; one **authenticated full scan**
   pre-launch.
4. **External pen test** — a scoped third-party test before the first paying
   customer. Proportionate to "first customers"; a continuous program belongs
   to the later "regulated scale" stage.
5. **Load + isolation test** — k6/Locust: N tenants × target RPS with the real
   connection pool. Watch p99, pool saturation, and **assert zero cross-tenant
   data in responses under concurrency** — this is the one isolation risk that
   unit tests structurally cannot cover.

---

## Sequencing

| Order | Phases | Gate | Status |
|---|---|---|---|
| 1 | Decision 0, Phase 2 (settings), Phase 4.1–4.2, 4.6 (CI) | `check --deploy` clean, deploys to staging | ✅ code landed, CI to confirm |
| 2 | Phase 1 (auth/authz/MFA) | negative auth tests green | ✅ code landed, needs a CI run (migrations) |
| 3 | Phase 3.1–3.2, 3.5 (pool mode, DB roles, state-machine fixes) | isolation test under a real pool | 🟡 state-machine + `granted_modules()` done; pool mode = ops (`.do/app.yaml` + DEPLOY.md); real-pool test still owed |
| 4 | Phase 4.3–4.5, Phase 5 (obs, backups, runbook) | first restore drill done, alerts firing | ✅ code + docs landed (`/health/ready`, celery hardening, JSON logs, Sentry, AuditLog, BACKUP_RESTORE.md, INCIDENT_RUNBOOK.md); drill + alert wiring are ops |
| 5 | Phase 6 baseline, Phase 7 (verification, pen test) | pen-test findings closed | 🟡 DPDP.md + `test_auth_isolation.py` landed; ZAP/pen-test/load-test are execution |
| later | Phase 3.3–3.4 fan-out tooling, WAF, k8s/ECS, formal compliance | when schema count / scale / a customer contract forces it | deferred by design |

**What only you can do** (not code): create the DO Postgres/Redis in BLR1 and
set the pool to `session` mode; run `.do/app.yaml`; set secrets; first
`createsuperuser` + TOTP enrol; the monthly restore drill; wire alert
destinations; commission the external pen test; run the k6 load+isolation test.

---

## Concrete code gaps in the repo today (checklist)

- [x] No auth endpoints; no custom user model — *`apps/accounts`: custom `User` (email login, `role`), per-schema (`auth`+`accounts` in `TENANT_APPS`), SimpleJWT login/refresh/logout/me, blacklist on rotation*
- [x] `apps/library/views.py` — `BookListView` is `AllowAny` — *now `RolePermission`*
- [x] `apps/hostel/views.py` — `RoomListView` no explicit permission — *now `RolePermission`*
- [ ] `apps/core/views.py` — empty stub *(no route points at it; delete or fill when a core API is needed)*
- [x] `library` / `hostel` were one-list stubs — *full CRUD + workflows (lending: issue/return/renew/fines/holds; hostel: allocate/vacate/waitlist/maintenance), row-locked inventory/capacity, pagination + django-filter + drf-spectacular, soft-delete, tests. See `docs/MODULES.md`.*
- [x] All three `admin.py` — nothing registered; admin on tenant URLconf — *`OTPAdminSite` at `/superadmin/`, public schema only, core models + `AuditLog` registered; admin removed from tenant URLconf*
- [x] `config/settings.py` — no `SECURE_*` / HSTS / secure-cookie — *added, gated on `DJANGO_ENV`; `config/env_guard.py` fails fast*
- [ ] `config/settings.py` — `DB_USER` defaults to `postgres` (superuser) — *documented in `DEPLOY.md` step 3; default left for local dev*
- [x] `apps/core/models.py` — `recompute_status()` / status-blind modules — *TERMINATED now preserved; `granted_modules()` added and middleware routed through it*
- [x] `config/celery.py` — no time limits / acks-late / result expiry — *all set; beat-singleton documented in `DEPLOY.md`*
- [x] `Dockerfile` — root, `gcc`, no `collectstatic`, no `.dockerignore` — *multi-stage, non-root, `collectstatic` at build, `gunicorn` CMD; `.dockerignore` added*
- [x] `docker-compose.yml` — `runserver` in prod path — *prod runs the Dockerfile `gunicorn` CMD on DO App Platform; compose is dev-only*
- [x] No CI / scanning — *`.github/workflows/ci.yml`: tests + `check --deploy` + `makemigrations --check` + `tsc`/`build` block; scanners informational until baseline triaged*
- [ ] `attendance` referenced in middleware + seed but no app — *feature work, out of scope for this plan*
- [x] `docs/FAILURE_MODES.md` / `docs/TESTING.md` — stale — *updated*
- [ ] `FAILURE_MODES.md §2` (search_path + pooling) — still needs a test under a real connection pool (Phase 7 load test)

### Files added/changed across all blocks

**Block 1:** `config/env_guard.py`, `config/settings.py`, `requirements.txt`, `Dockerfile`,
`.dockerignore`, `.env.example`, `.github/workflows/ci.yml`, `frontend/next.config.js`.

**Blocks 2–5:** `apps/accounts/*` (new app + hand-written `0001_initial`),
`apps/core/{models,middleware,audit,admin,apps}.py`, `apps/core/migrations/0002_auditlog.py`,
`config/{admin,health,logfmt,urls,urls_public,celery,settings}.py`,
`apps/{library,hostel}/views.py`, `apps/core/tests/test_subscription_state_machine.py`,
`apps/accounts/tests/test_auth_isolation.py`, `requirements.txt`, `.do/app.yaml`,
`docs/{DEPLOY,BACKUP_RESTORE,INCIDENT_RUNBOOK,DPDP}.md`, `docs/{FAILURE_MODES,TESTING}.md`.

**Not verifiable in the authoring environment** (no venv / Django 5 / Postgres): migrations,
test suites, `check --deploy`, the Docker build, the admin site. Verified here: every `.py`
AST-parses, `config/env_guard.py` self-check passes, CI + `.do/app.yaml` YAML parse. The
hand-written `apps/accounts/migrations/0001_initial.py` is the highest-risk artifact — CI's
`makemigrations --check` will flag any drift; regenerate with `makemigrations accounts` if so.
