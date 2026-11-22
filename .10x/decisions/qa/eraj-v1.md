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

## M5 Transport + Inventory (2026-11-22)
- `apps.transport` 11 tests (TR-1…6 + capacity by dates, mid-month stop, change of stop, staff riders,
  over-speed, key rotation, guards); `apps.inventory` 10 tests (INV-1…5, weighted average, HR-1
  inventory half, mess cost per head, guards). Full suite in status.md.
- Browser: smoke-m5 21/21 (live map + trip, assign → fee posted, stop from next month, full vehicle
  refused, rider list PDF, expiring papers; direct purchase, returnable issue, damaged return in the
  ledger, store keeper can't adjust, ₹60,000 requisition → accountant + Admin approvals → order →
  60 % received, PO PDF, Admin adjustment, low stock, mess cost per head). Regression m1–m4 green.
- Bugs found and fixed: relation selects weren't linked to their form labels (`id` dropped) — now
  accessible and testable by label; demo transport riders collided with the fees walkthrough's
  students (seed now leaves them out); OpenAPI name clashes (Issue, Reason).
- TR-6 "position under a minute old" and the parent alert are proven with the push endpoint and the
  log-only notifier; a real tracker/provider and real SMS/WhatsApp delivery remain to be tested (GPS
  provider not yet named; channels in M6).

## M6 Alerts + Portal + Learning (2026-11-22)
- `apps.notify` 10 tests (ALR-1…4, quiet hours, opt-out, fallback, receipts, retries); `apps.learning`
  10 (LRN-1…4 staff side, attachments by content, late, class window, test time cap, questions locked,
  teacher scope, reports); `apps.portal` 14 (PORTAL-1…5, OTP unknown number/rate limit/lockout/
  expiry, endpoint-by-endpoint IDOR sweep over every child route and method, staff/other parents see
  nothing, LRN-1 parent side, student test + join, leave → attendance, change request, notice reads).
- Browser: smoke-m6 22/22 on a 390 px phone viewport for parent/student and desktop for staff —
  OTP login, two children, absent shows at once, receipt + published report card (unpublished 404),
  outpass → warden → approved, another child by URL refused, PDF attached / photo submitted / graded
  / grade on portal, late flag, class in timetable + join record, 10-question test scored, notice
  read receipt, leave → class teacher, change request applied on approval, OTP never readable in
  the log, all new staff screens open. Regression m1–m5 green (see status.md).
- Bugs found by the walkthrough and fixed: portal home never loaded (empty path treated as "no
  request"); range pickers overflowed a phone screen (now two single date pickers); two children
  with the same first name looked identical on the switcher.
- Bugs found by tests and fixed: a wrong OTP try was rolled back with the refusal (5-try limit never
  held); guardian phones stored with spaces/+91 didn't match; row lock on an outer join (change
  requests).
- Not covered here: real SMS/WhatsApp delivery (DLT pending; WhatsApp account not connected) — the
  adapters are tested against a stubbed HTTP layer; staging runs log-only.
