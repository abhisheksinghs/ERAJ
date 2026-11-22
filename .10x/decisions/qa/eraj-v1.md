# QA — eraj-v1

## M4 HR + Payroll (2026-11-22)
**Strategy:** one Django test per acceptance scenario (HR 1–4, Payroll 1–8) with figures worked by
hand in the test comments; calculator unit tests (TDS projection, rebate, ESI ceiling, EPS split,
negative net); negative tests for permissions, cross-branch writes, self-service scope, locked
months; one browser walkthrough (`e2e/smoke-m4.mjs`) across HR, accountant, Admin and teacher.

**Results**
- `apps.hr` 14 tests, `apps.payroll` 22 tests — all pass (full suite numbers in status.md).
- Browser: smoke-m4 20/20; regression smoke-m1 14/14, m2-fees 19/19, m2-hostel 12/12,
  m3 14/14, m3-timetable 10/10 (each on a fresh `seed_demo_tenants`).
- `next build` ok; `npm audit` 0 after Next 16.4.3 → 16.4.6.

**Bugs found and fixed during M4**
- PAN/IFSC typed in lower case were rejected (validators ran before upper-casing) → normalised first.
- A staff object held in memory could still get leave after exit → status read from the DB.
- `increment_month` validation rejected structures that didn't send the field.
- HR staff list serializer not branch-scoped (router guard caught it).
- OpenAPI enum/component name clashes (Decision, status, gender) → renamed / overridden; 0 warnings.

**Scenario interpretation (for the client's sign-off)**
- PAY-2 "net drops by exactly 2 days' pay": true for staff without percentage deductions (tested
  to the rupee). For PF/NPS/ESI members earnings drop by 2 days and the % deductions are
  recomputed on the reduced wages, as payroll practice requires.
- PAY-5 and PAY-6 are signed off by the client's accountant on real data and the EPFO portal;
  tests prove arithmetic and file format only.

**Not covered yet:** concurrency test for two approvers on the same balance (guarded by
`select_for_update`); payslip Hindi rendering (uses the same fonts as receipts, verified in M0).
