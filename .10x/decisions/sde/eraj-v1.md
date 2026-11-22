# SDE — eraj-v1

## M0 (done 2026-10-25)
Next 16.4.3 + React 19.3.1 + Refine 5 + AntD 5.29.3 (Refine's AntD package peers antd ^5);
`path-to-regexp` overridden to 8.4.2; npm audit 0. psycopg2-binary 2.9.13; WeasyPrint 70 + Noto
fonts (Hindi PDF verified: conjuncts + ₹ render, fonts embedded); openpyxl. `middleware.ts` →
`proxy.ts` (Next 16); cookies()/headers() now async.

## M1 backend (done 2026-10-25)
- `apps.org`: Branch, BranchOwned, Role, RoleAssignment (+constraints), `rbac.PERMISSIONS`
  (fnmatch, `-` deny), `scope.resolve_scope` (X-Branch), `HasPerm` (default deny),
  `BranchScopedViewSetMixin`, `ScopedPrimaryKeyRelatedField`, `BranchScopedSerializer`,
  Branch + User (roles) ViewSets.
- `apps.people`: AcademicYear, Department, Program, Term, Subject, Staff, Student, Guardian,
  StudentGuardian, Section, Enrollment; Excel/CSV import (validate-all-then-write, dry run).
- All 9 modules ported to branch scope + registry FKs (Library Member = student XOR staff;
  Hostel residents = students; Attendance/Exam use people.Student/Subject; HR models moved to
  people; Payroll pays people.Staff). Feature depth unchanged for lean modules (M2–M5).
- `create_tenant` → first Branch + owner (Admin + Group admin) + current academic year (Apr–Mar).
- `seed_demo_tenants` → abc (1 branch), pqr (patna + gaya, demo staff users, students, books, rooms).
- `StandardPagination` (`page_size` up to 200); OpenAPI: 0 warnings.
- Tests: 62 Django + 23 pytest green in one run. New: router guards (4), RBAC map, branch
  isolation (11), user management (4), import (5).

### Deviations from plan
- RoleAssignment lives in `apps.org`, not `apps.accounts` (accounts is also a public-schema app;
  public has no branch table). Recorded in ADR-006 consequences.
- Media switched to per-tenant storage (not in plan; found during M1 — student photos).

### Tech debt created
- Lean modules still have M0-era depth; Fees `Payment.receipt_no` is uuid-based until M2 ledger.
- Some list columns show related ids (holds, waitlist, fines) until serializers add names.

## M1 frontend (done 2026-10-25)
Refine shell: same-origin proxy (`/api/proxy/*`) with silent refresh (rotated refresh token) and
Origin check on writes; session context (me, branch, language) with the rbac patterns evaluated
client-side for menus/buttons; resource registry `lib/resources.ts` (33 screens, en/hi);
generic `ResourceList` / `ResourceForm` / `ImportModal`; dashboard; bilingual sign-in;
402 → renewal screen; bilingual toasts.

### Bugs found by the browser walkthrough (fixed)
- `GET /api/library/members/` 500: `Member.open_loan_count` property clashed with a queryset
  annotation of the same name (pre-existing in the old code). Annotation renamed `loans_open`;
  regression test `test_member_list_reports_open_loans`.
- Every staff role saw a Settings menu (branch list via `org.branch.view` in REGISTRY_READ).
  Removed; branch names for the switcher come from `/auth/me`.
- Default branch was alphabetical; now the branch where the user holds a working role.
- Refine toasts showed raw keys ("notifications.success", "library/issue").

## M4 HR + Payroll (done 2026-11-22, ADR-009)
Backend
- `apps.hr`: StaffProfile (payroll identity, masked lists), Designation, StaffDocument (checked,
  private download), StaffAttendance (one-save day sheet, punches → present, register + PDF),
  LeaveType/LeaveBalance/LeaveApplication (pending reserved, approve/reject/cancel, unpaid → LOP),
  exit, reports (headcount, balances, absentees), self-service `/api/hr/me/*`.
  `staff_on_leave()` now feeds timetable substitution; staff punches feed HR attendance.
- `apps.payroll` rewritten: rule sets (matrix, DA history, HRA X/Y/Z, components), statutory
  settings, structures (+ per-staff overrides), pure `calc.py`, run lifecycle (create with
  increments → recompute → review → lock → Admin reversal), DA arrears with `ArrearPayment`
  markers, loans with `LoanRecovery`, one-time payments, exports (payslip PDF, bank sheet, register,
  ECR, ESIC, PT, 24Q, Form 16, statutory summary, YTD), own payslips for staff.
- People staff list defaults to active staff (`?status=left|all` for history).
- RBAC: `STAFF_SELF` (hr.self.*, payroll.self.view) for every staff role; accountant gets
  hr.profile.view + hr.attendance.view; HR can't correct past attendance (Admin only).
Frontend
- Registry: HR module (staff joining & exit, profiles, designations, leave applications,
  balances, leave types, attendance records); Payroll (monthly payroll with workflow + file links,
  payslips, structures, loans, bonus & arrears, pay rules, pay matrix, components, DA history,
  statutory settings). Pages: /hr/mark, /hr/documents, /hr/reports, /hr/me, /payroll/da,
  /payroll/reports. Action bodies support `{today}`.
- Next.js 16.4.3 → 16.4.6 (npm audit advisories).
Demo data: HR role users; leave types; profiles; central + Bihar sample rule sets; PF/NPS/ESI
structures; advance; last month's attendance and payroll locked; this month's in draft.

### Deviations
- Inventory "issue to staff" (HR-1 second half) waits for M5's inventory rebuild; HR-1 test covers
  Library and the shared staff list Inventory will use.
- Arrear PF/NPS is deducted in the paying month and included in that month's ECR wages
  (no separate arrear ECR) — accountant to confirm.

### Tech debt
- Payroll run list shows `month` as a date (01-11-2026), not "Nov 2026".
- `hr/documents` is a hand-built page (generic form has no file field yet).
- TDS: new-regime projection only; old-regime staff use the fixed monthly figure.

## M5 Transport + Inventory (done 2026-11-22, ADR-010)
- `apps.transport` rewritten: routes + ordered stops (times, lat/lng, distance, fare), fare slabs,
  vehicles (driver/helper, GPS key), papers with expiry, student/staff assignment with capacity by
  date, monthly transport charges (fees ledger), stop/change from a date, GPS push + simulator +
  `simulate_gps` command, speed / near-stop / paper alerts (log-only notifier), live/trip data,
  rider list PDF/Excel, occupancy, expiring papers. `core.notify.staff_role()` added.
- `apps.inventory` rewritten: stores (mess store linked to a Mess), vendors (GSTIN), items, stock
  ledger with weighted average cost, opening stock, issue/return/damaged/lost, Admin adjustment,
  requisitions with approval levels, numbered POs with PDF, part/full goods receipts, direct
  purchases, reports. Hostel `cost-per-head` endpoint.
- Frontend: registry entries for both modules; pages /transport/live (Leaflet + OSM),
  /transport/assign (assign or change), /transport/reports, /inventory/stock, /inventory/receive,
  /inventory/reports. Create forms can be pre-filled from the URL; action bodies support
  `{next_month}`; relation selects receive the Form.Item `id`.
- Deviations: requisitions are raised by the store keeper/Admin for a department (no teacher login
  for requisitions yet); staff transport is free (no payroll deduction).
- Tech debt: OSM public tiles (switch to a paid tile provider at scale); daily paper-reminder task
  not yet on Celery beat (M7 with the other periodic jobs).
