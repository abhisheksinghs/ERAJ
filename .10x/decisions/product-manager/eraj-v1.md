# Product Manager — eraj-v1

**Date:** 2026-10-25 · **Spec:** `.10x/specs/2026-10-25-eraj-v1-scope.md`

## Users
Admin, Group Admin, Accountant, Teacher, Librarian, Warden, Transport in-charge, HR, Store
keeper, Parent, Student — at schools, colleges and coaching centres of varying size, possibly
multi-branch, in Bihar (central + Bihar state pay rules, Hindi).

## Success criteria
1. 2026-11-11: every module reachable on staging with its core flows working end to end.
2. Then: every numbered acceptance scenario in the client scope doc passes on staging with the
   client's own data; client signs off module by module.

## Priority inside each module when time runs short (cut from the bottom)
1. Core records + the module's main workflow (issue/return, allocate, mark, collect, run payroll …)
2. Rules that protect money or data (locks, approvals, concessions, cancellations, isolation)
3. Reports and exports
4. Prints/PDFs
5. Integrations beyond fakes (real SMS/GPS/biometric), Tally export, ECR format, online tests, class diary

## Out of scope
As listed in the scope doc (online payment, native apps, admissions, auto timetable, built-in
video, filing on govt portals, live Tally sync, hardware/subscriptions).
