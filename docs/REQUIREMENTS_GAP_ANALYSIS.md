# Requirements Gap Analysis — vs. `Final_SaaS_Multi_Product_Architecture.pdf`

Source: the user-supplied spec, 9 sections. This document maps each section to
the current codebase, flags real gaps, and gives a sequenced implementation
plan. No code changed in this pass — analysis only.

## Verdict at a glance

| PDF requirement | Eraj status | Verdict |
|---|---|---|
| One codebase, shared core (auth/tenant/subscription/billing/permissions) | `apps/core` + `apps/accounts` shared across all tenant schemas | ✅ met (billing is data-only, see below) |
| Multiple products/modules in one codebase | Library, Hostel built; Attendance/HR/Payroll/Fees/Exam/Transport/Inventory not | 🟡 **2 of 9** |
| Per-product domain (`library.yourcompany.com`) + per-tenant sub-subdomain (`abc.library...`) | Per-**tenant** domain (`abc.eraj.com`) + per-product **URL path** (`/api/library/...`) | ❌ **different model — see Finding 1** |
| Many clients per product, isolated data | schema-per-tenant (django-tenants) — stronger than the PDF's implied `tenant_id` column | ✅ met, exceeds spec |
| Plans gate which products a client gets | `Plan` / `Module` / `PlanModule` / `Subscription` — exact match to the PDF's model | ✅ met |
| Super Admin flow: create client → pick products → pick plan → price → duration → activate | Data model + Django admin CRUD support every step manually; no guided/atomic flow | 🟡 partial |
| Expired tenant sees a renewal page | Backend returns 402 JSON; frontend shows a generic error, no renewal page | ❌ gap |
| Tenant-isolated data | Schema-per-tenant | ✅ met, exceeds spec |
| Common deployment, no per-client app | One Django backend, one Next.js frontend, one deploy | ✅ met |
| New products added without duplicating the codebase | Proven this session — Library and Hostel both landed via the same models → services → API pattern | ✅ met |

---

## Finding 1 — domain model differs from the spec (the one architectural decision worth a call)

**Spec wants:** product identifies the domain, tenant is a sub-subdomain of
the product:
`library.yourcompany.com`, then `abc.library.yourcompany.com` /
`xyz.library.yourcompany.com` per client.

**Eraj built:** tenant identifies the domain, product is a URL path under it:
`abc.eraj.com/api/library/...`, `abc.eraj.com/api/hostel/...`.

This is not an oversight in the sense of "forgot to build it" — it's a
different, internally-consistent design that satisfies every *functional*
requirement in the PDF (isolation, per-module plan gating, one shared
codebase, one deploy). What it does **not** give you is a product having its
own branded top-level domain.

It IS worth fixing as a documentation bug: `docs/ARCHITECTURE.md`'s "Request
flow" (`abc.library.eraj.com`) and "Frontend" section (subdomain → product
route group) describe the PDF's product-per-domain model — a design that was
apparently intended at some point but never built. The code has always used
path-based routing. Right now the docs contradict the code.

**Recommendation: keep path-based routing, fix the docs.** Rationale:
- Product-per-domain means wildcard SSL and DNS automation *per product, per
  tenant* (`docs/ARCHITECTURE.md` already lists this as explicitly
  out-of-scope) — real ops cost for a URL-structure preference, not a
  functional gain.
- The PDF's own text: *"Important: different domains do NOT mean different
  codebases."* The domain layer is presentation, not architecture.
- If a specific product later needs a standalone marketing domain
  (`library.eraj.com` pointing at the same backend, same tenant resolution
  by an added header/cookie), that's a reverse-proxy addition, not a rewrite.

**If you want the literal PDF model instead**, say so — it changes
`TenantMainMiddleware`'s resolution logic, `frontend/middleware.ts`, every
`Domain` row, and the whole DNS/SSL story, and should be scoped as its own
plan before any module work continues.

---

## Section-by-section detail

### §1–2 Overall architecture / one codebase
Match. `apps/core` (Client, Domain, Plan, Module, PlanModule, Subscription,
AuditLog — public schema) + `apps/accounts` (per-schema auth) play the PDF's
"Core" role. `apps/library`, `apps/hostel` play "Modules/". Django admin at
`/superadmin/` is the closest thing to the PDF's "SuperAdmin/" folder — it's
generic CRUD, not a purpose-built console (see §7).

### §3–4 Multiple modules / multiple domains
Library and Hostel are built to full workflow depth (`docs/MODULES.md`).
Attendance, HR, Payroll, Fees, Exam, Transport, Inventory are not — see the
implementation plan below. Domain-per-product: see Finding 1.

One dangling reference: `apps/core/middleware.py` `MODULE_PATH_PREFIXES` and
`seed_demo_tenants` both reference an `attendance` module/plan entry, but
`apps/attendance` doesn't exist — any request to `/api/attendance/*` 403s
correctly (module not licensed) rather than 404ing on a missing app, so
nothing is broken, but it's a half-finished reference.

### §5 Multiple clients/tenants, data isolation
Exceeds the spec. django-tenants gives each client a real Postgres schema
instead of a shared table + `tenant_id` filter — see
`docs/ARCHITECTURE.md`'s "Decision" section and
`apps/library/tests/test_tenant_isolation.py`, which proves it against a real
database rather than trusting every query to remember the filter.

### §6 Plans & pricing
Match, field-for-field: `Plan.price_per_year`, `Plan.is_custom`, `Module`,
`PlanModule` (which modules a plan includes), `Subscription` (per-client
plan + status + dates). `seed_demo_tenants` only seeds Basic/Standard — add
Premium/Custom rows when there's a real client to sell them to (data, not
code).

### §7 Super Admin control flow
The **data model** supports the whole flow
(`Client Create → Select Product(s) → Select Plan → Set Price → Set Duration
→ Activate Subscription`) and Django admin can execute every step. What's
missing:
- **One atomic onboarding action.** Today it's: create `Client` (triggers
  schema creation) → create `Domain` → create `Subscription` — three
  separate admin screens, no rollback if step 2 fails. (This was already
  flagged in `docs/PRODUCTION_READINESS.md` Phase 3.4.)
- **Renewal page.** The PDF explicitly calls this out: *"The expired tenant
  can be shown a renewal page."* Backend already returns a clean 402 with
  `{"error": "subscription_inactive", "status": ...}` — the frontend has
  nothing rendering a renewal CTA on that response, it shows the generic
  notice text.
- **Billing.** `Plan.price_per_year` is a number; there's no invoice, no
  payment provider, no "mark this subscription paid" action beyond directly
  editing `Subscription.status` in admin. Already flagged as out of scope in
  `ARCHITECTURE.md` and `PRODUCTION_READINESS.md`.

### §8 Request flow / data isolation
The PDF's flow (*Identify Product Domain → Identify Tenant → Check
Subscription → Check Module Permission → Load Tenant Data → Show Product*)
maps onto Eraj's actual flow one-for-one except the first step, which is
"Identify Tenant" first (via subdomain), then "Identify Module" via URL path
inside `SubscriptionEnforcementMiddleware` — a consequence of Finding 1, not
a missing check. Every enforcement step in the PDF is present.

### §9 Final business model
All eight rows in the PDF's summary table hold, with two caveats already
covered above: "Domains" (Finding 1) and "Products" (2 of 9 built).

---

## Implementation plan for what's actually missing

Ordered by dependency and value; each module follows the pattern this
session established for Library/Hostel: models (no tenant FK) → `services.py`
for anything with a business rule → serializers → ViewSet + router → tests →
migration. See `docs/MODULES.md` for the reference shape.

| # | Item | Status |
|---|---|---|
| 1 | Fix `docs/ARCHITECTURE.md` to describe the actual (path-based) routing | ✅ done |
| 2 | Resolve the dangling `attendance` reference | ✅ done — module built (item 3) |
| 3 | **Attendance module** | ✅ done — lean tier: `Student`, `AttendanceRecord`, idempotent `mark`, `summary` report |
| 4 | **Frontend renewal page** | ✅ done — `StatusNotice` component, dedicated 402 CTA |
| 5 | **Tenant onboarding as one atomic action** | ✅ done — `manage.py create_tenant`, rolls back the schema on any failure |
| 6 | **HR module** | ✅ done — lean tier: `Department`, `Employee`, pure CRUD |
| 7 | **Fees module** | ✅ done — lean tier: `FeeStructure`, `Payment`, receipt generation, collections report. No dues/invoicing (needs enrollment model — still open) |
| 8 | **Payroll module** | ✅ done — lean tier: `Payslip` off HR's `Employee`, flat net-pay math, explicitly **not** statutory-compliant |
| 9 | **Exam module** | ✅ done — lean tier: own `Student`, `Subject`, `ExamResult`, idempotent recording + report |
| 10 | **Transport module** | ✅ done — lean tier: `Route`, `Vehicle`, `TransportAssignment`, row-locked capacity check |
| 11 | **Inventory module** | ✅ done — copy-adapted from Library's Book/Issue pattern |
| 12 | **Notifications** (core service the PDF lists) | still deferred — no trigger exists yet to hang it off |
| 13 | **Billing/payment provider integration** | still deferred — needs a provider decision first |
| 14 | **Frontend pages for the 7 new modules** | not built this pass — same `app/library/page.tsx` pattern applies; scope cut to keep this pass reviewable |
| 15 | **Shared "Student" registry** | deliberately not built — see `docs/MODULES.md`'s note; revisit if duplicate data entry becomes a real complaint |

All 7 new modules are **lean tier**: CRUD + the one core action each
obviously needs, no invented compliance/grading/routing logic with no real
spec behind it. Not run against a live Django/Postgres — see the caveat at
the end of this document.

**Note on a shared "Student" concept:** Attendance, Fees, and Exam all
independently need a person to attach records to. Library already has
`Member`, Hostel has `Resident` — neither is reusable as-is (different
fields, different lifecycle). Before building Fees/Exam, decide: one shared
`apps.core` "Student" model (SHARED_APPS, public schema) that Attendance/
Fees/Exam all FK into per-schema... except FKs can't cross a shared/tenant
boundary cleanly under django-tenants. Realistic options: (a) each module
keeps its own person record (current Library/Hostel pattern — some
duplication, zero cross-module coupling, matches "modules stay independent"
from the PDF's own §3), or (b) a tenant-scoped `apps.people` app with a
canonical `Student`/`Staff` model that the other modules FK into. **(a)
matches what's already built and the PDF's "each module... independent"
language; recommend it** unless duplicate data entry across modules becomes
a real complaint.

## Status

Items 1–11 landed. `seed_demo_tenants` now seeds the PDF's own three-tenant
example verbatim: ABC/Basic/Library, XYZ/Standard/Library+Hostel+Attendance,
PQR/Premium/Library+Hostel+Attendance+HR+Payroll. Remaining: notifications,
billing, frontend pages for the 7 new modules, and the shared-Student
question — all explicitly deferred above, not oversights.

**Not verified against a live Django/Postgres or `next build`** — same
constraint as every prior pass this session. Highest risk: 7 new
hand-written `0001_initial` migrations. Structurally lower risk than the
earlier *additive* migrations (`accounts/0001`, `library/0002`,
`hostel/0002`) — these are brand-new apps, so each migration only has to
match the models.py written in the same commit, not reconcile against
pre-existing columns. `makemigrations --check` in CI (informational) is
still the backstop.
