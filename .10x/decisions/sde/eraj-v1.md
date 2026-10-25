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
