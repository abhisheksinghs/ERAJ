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

| # | Item | Why this order | Rough size (vs. Library/Hostel build) |
|---|---|---|---|
| 1 | Fix `docs/ARCHITECTURE.md` to describe the actual (path-based) routing | Docs actively contradict the code today — cheapest, highest-confusion-reduction fix | trivial |
| 2 | Resolve the dangling `attendance` reference — either build the module (next item) or remove it from `MODULE_PATH_PREFIXES`/seed until it exists | Currently harmless (403s cleanly) but misleading | trivial |
| 3 | **Attendance module** — daily student/staff attendance records, per-date marking, a summary/percentage report | Smallest new module (2 models, no complex workflow); the `attendance` Module row already exists in the data model and plan | ~⅓ of a Library-sized build |
| 4 | **Frontend renewal page** — a `/billing` (or reuse `/`) page that recognizes the 402 shape and shows a renewal CTA instead of the generic notice | Directly named in the PDF; small, isolated frontend change | small |
| 5 | **Tenant onboarding as one atomic action** — a management command or superadmin API endpoint wrapping Client+Domain+Subscription (+owner user) creation in one transaction, rollback (schema drop) on failure | Closes the §7 "Super Admin flow" gap without building a full admin UI | small–medium |
| 6 | **HR module** — employee records, department, designation | No dependents; standalone | ~½ of a Library-sized build |
| 7 | **Fees module** — fee structure per plan/term, collection, receipts, dues | References Members/Residents conceptually but no hard FK dependency; can stand alone against a generic "Student" concept (doesn't exist yet — see note) | ~ Library-sized |
| 8 | **Payroll module** — depends on HR's employee records | Build after HR so it has a real FK target instead of a stub | ~ Library-sized |
| 9 | **Exam module** — exams, marks, results | Standalone; needs a "Student" concept shared with Fees/Attendance (see note) | ~ Library-sized |
| 10 | **Transport module** — routes, vehicles, student assignment | Standalone, lowest business complexity of the remaining set | ~⅓ of a Library-sized build |
| 11 | **Inventory module** — stock items, issue/return (structurally similar to Library's `Book`/`Issue`) | Last — smallest incremental design cost once the Library pattern exists, but lowest priority in the PDF's own ordering | ~⅓ of a Library-sized build, mostly copy-adapt from Library |
| 12 | **Notifications** (core service the PDF lists) | Needed once Fees/Exam/renewal flows want to alert someone; premature before those exist | small, once triggered by something real |
| 13 | **Billing/payment provider integration** | Explicitly deferred in every prior planning doc this session; needs a provider decision first | separate plan |

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

## What I'd do next

Items 1–2 are a five-minute cleanup and can go out immediately. Item 3
(Attendance) is the natural next module — it completes the exact three
products (`Library + Hostel + Attendance`) the PDF uses as its own worked
example for the "Standard" plan. Items 4–5 close the two concrete PDF
requirements (renewal page, onboarding flow) that aren't about new modules
at all. Say which of these to execute and I'll build it the same way as
Library/Hostel — code, tests, docs, one commit.
