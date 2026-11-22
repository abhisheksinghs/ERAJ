# Senior Engineer — eraj-v1

**Date:** 2026-10-25

## M0/M1 approach
1. `requirements.txt`: `psycopg2-binary>=2.9.10`; add `weasyprint`, `openpyxl`.
2. Remove module migrations; build `apps.org`, `apps.people`; rework module models onto
   people FKs + `BranchOwned`; `makemigrations` fresh; `migrate_schemas` on a dropped DB.
3. `accounts`: drop `role`; add `RoleAssignment`; `rbac.py`; `HasPerm`; `/auth/me` payload;
   token gains `branches` claim is NOT needed — branch checked server-side per request.
4. `org/mixins.py`: `BranchScopedViewSetMixin` (reads `X-Branch`, validates against
   assignments, filters, stamps on create); `tests/test_router_guards.py` walks all routers
   and asserts every ViewSet over a `BranchOwned` model uses the mixin and every action has a
   declared permission.
5. `create_tenant` + `seed_demo_tenants`: create default Branch + Admin assignment + demo
   people data.
6. Frontend: Next upgrade; install Refine/AntD; `app/(staff)/layout.tsx` with Refine provider,
   `lib/dataProvider.ts` (DRF), `lib/accessControl.ts`, `app/api/proxy/[...path]/route.ts`;
   login page reuses existing BFF cookie route; branch switcher stores branch id in a cookie
   the proxy forwards as `X-Branch`.

## Tricky parts
- django-tenants + `TenantTestCase`: all tests that touch tenant models must run inside the
  test tenant; fixtures create a Branch first.
- Refine + Next App Router SSR: staff area renders client-side (`"use client"` providers);
  auth check happens in middleware + proxy, not in the browser.
- Refine/AntD version pinning against the upgraded Next major.

## M4 approach (2026-11-22)
1. HR models + services: `mark_day`, `apply_punches`, `apply_leave`/`approve`/`reject`/`cancel`,
   `exit_staff`, `staff_on_leave`, `lop_days(staff, month)`; reports in `hr/reports.py`.
2. Staff list default = active (people view) unless `status` param present.
3. Payroll calculator as pure functions over plain inputs (structure snapshot, settings, LOP,
   loans, one-time, prior payslips) → lines; unit-tested without HTTP.
4. Run lifecycle services: `create_run` (increments, compute), `recompute`, `submit`, `back_to_draft`,
   `lock` (loan balances, arrear markers), `reverse` (Admin, reason).
5. Exports: payslip PDF, bank sheet, register, ECR, ESIC, PT, 24Q, Form 16, YTD.
6. Scenario tests HR-1…4, PAY-1…8 + negatives (cross-branch, teacher denied, self-service only
   own records).
Tricky: rounding (whole rupees per line, ESI ceil), TDS remaining months in FY (Apr–Mar),
arrears for months with LOP (prorate by that month's paid days), lock guard on HR edits.

## M5 approach (2026-11-22)
1. Transport models + services: `fare_for(stop)`, `assign`, `stop`, `change`, `ingest_position`
   (speed + near-stop alerts, haversine), reports; GPS push view; `simulate_gps` command.
2. Inventory models + services: `receive_into_stock` (weighted avg), `issue`, `return_issue`,
   `adjust`, requisition `submit/approve/reject`, `raise_po`, `receive`, `direct_purchase`;
   PO PDF; reports.
3. Hostel `cost_per_head(mess, month)`.
4. Scenario tests TR-1…6, INV-1…5, plus HR-1 inventory half; negatives (cross-branch, role).
5. Frontend registry + pages: live map, rider lists/reports, stock reports, goods receipt.
Tricky: capacity overlap by dates; mid-month stop; decimals in quantities (kg/litre) — qty is
Decimal(12,3); PO numbering counter per FY.
