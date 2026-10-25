# SDE — index

## [DISCOVERED] What is built (2026-10-25)
| Module | Backend depth | Frontend |
|---|---|---|
| Library | Full workflow: catalogue, members, issue/return/renew, fines (waive owner-only), holds, ISBN lookup | Read-only list |
| Hostel | Full workflow: rooms, residents, allocate/vacate (row-locked), waitlist, maintenance blocks allocation | Read-only list |
| Attendance | Lean: Student, idempotent mark, summary % | None |
| HR | Lean: Department, Employee CRUD | None |
| Payroll | Lean: Payslip with flat net-pay maths (not statutory) | None |
| Fees | Lean: FeeStructure, Payment + receipt no., collections total; no per-student dues | None |
| Exam | Lean: Student, Subject, ExamResult, report % | None |
| Transport | Lean: Route, Vehicle, row-locked capacity assignment | None |
| Inventory | Lean: Item, IssueRecord (Library pattern) | None |

Platform: tenant onboarding command (`create_tenant`, atomic), subscription state machine,
AuditLog, JSON logs, Sentry hook, `/health` + `/health/ready`, Celery hardening, CI workflow,
DO App Platform spec (`.do/app.yaml`).

## Active features
| Slug | File | State |
|---|---|---|
| eraj-v1 | (not started) | — |
