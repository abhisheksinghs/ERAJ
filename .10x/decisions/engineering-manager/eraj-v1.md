# Engineering Manager — eraj-v1

**Date:** 2026-10-25 · **Team:** owner (full-time, reviews + client) + AI build · **Deadline:** staging 2026-11-11

## Milestones
| ID | Dates | Deliverable | Gate |
|---|---|---|---|
| M0 | 25 Oct | Dep fixes, Next upgrade, Refine shell builds, CI green locally | `pytest`, `next build` pass |
| M1 | 25–27 Oct | org, people, accounts RBAC, branch mixin, bulk import, fresh migrations, staff shell with login + branch switcher + people screens | isolation + rbac tests green |
| M2 | 28–30 Oct | Fees ledger; Library; Hostel + Mess + visitors/outpass | scenario tests for these modules |
| M3 | 31 Oct–2 Nov | Attendance (daily/lecture, punches); Exam (+SGPA/CGPA, report card PDF); Timetable + substitution | scenario tests |
| M4 | 3–5 Nov | HR (leave, staff attendance, docs); Payroll (two rule sets, matrix, DA arrears, run/lock, payslip PDF, statutory files) | scenario tests |
| M5 | 6–7 Nov | Transport (+GPS simulated); Inventory (+requisition/PO/GRN) | scenario tests |
| M6 | 8–9 Nov | notify + integrations (WhatsApp/email real, SMS/GPS fake); Portal; Learning | scenario tests |
| M7 | 10 Nov | Hindi strings pass; import templates; staging deploy | smoke test on staging |
| M8 | 11 Nov | Run scenario list on staging; QA + security reports | reports written |

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Push access not granted | Medium | Work locally; push in one go when granted (B1) |
| Staging host not ready by 5 Nov | Medium | Fallback: single VM + docker compose |
| Payroll rules unclear (which staff on which rule set) | High | Rule sets are data; ship engine + Bihar/central sample config, client fills real values |
| Scope too large for 17 days | High | PM cut order (`product-manager/eraj-v1.md`); daily status update |
