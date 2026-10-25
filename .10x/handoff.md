# Handoff

**From:** M2 (2026-10-25) **To:** SDE — M3

- M2 built and pushed: Fees ledger + staff screens (counter, reports, dues/defaulters, receipts,
  concessions, plans with instalment editor, Tally), library fines billed to Fees, Hostel blocks /
  rooms / fee rules / residents / waiting list / repairs, Mess (ADR-007: monthly in advance with
  leave rebate, per-day in arrears, guest meals, headcount, contractor bill, menu PDF, complaints),
  Gate (approved visitors, held visitors, outpass with parent alerts and automatic mess leave).
- Verification: 112 Django tests + 26 pytest, CI green (lint, drift, every app's tests, deploy
  check). Browser: `e2e/smoke-m1.mjs` 14/14, `e2e/smoke-m2-fees.mjs` 19/19,
  `e2e/smoke-m2-hostel.mjs` 12/12 (each needs a fresh `seed_demo_tenants`).
- Not yet built for M2 scope: hand-built occupancy board / headcount / contractor-bill pages (the
  APIs exist: `hostel/rooms/board`, `hostel/messes/headcount`, `hostel/messes/{id}/contractor-bill`);
  Celery beat entries for `bill_mess_month` (1st) and `apply_late_fines` (daily) per tenant;
  provisions + cost per head (needs Inventory "Mess store", M5); real parent alerts (M6).
- M3 order: Attendance (daily/per-lecture, device adapters + CSV punch import), Exam (grade bands,
  SGPA/CGPA, report cards), Timetable + substitution. ADR first for device adapters.
- Commits: author Abhishek Singh, no AI attribution.
