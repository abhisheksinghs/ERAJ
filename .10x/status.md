# Eraj — Project Status

**Phase:** Planning Complete → Implementation (M0)
**Updated:** 2026-10-25
**Target:** all modules running on staging by **2026-11-11** (owner on leave, full-time); client acceptance testing after that.
**Scope source:** `.10x/specs/2026-10-25-eraj-v1-scope.md` (summary of the client scope doc)

## Blockers
| # | Blocker | Owner | Needed by |
|---|---|---|---|
| B1 | Claude has no push access to `abhisheksinghs/eraj` — install the Claude GitHub App on the repo or reconnect GitHub in claude.ai settings | Abhishek | before first push (work continues locally until then) |
| B2 | Staging hosting account (DigitalOcean BLR1, or a VPS) + domain/DNS for `*.staging` subdomains | Abhishek | ~2026-11-05 |
| ~~B3~~ | ~~Branch model decision~~ — resolved 2026-10-25: branch rows inside client schema (ADR-001) | — | — |

## Phase log
| Phase | State | Notes |
|---|---|---|
| Discovery | Done | Verified live on 2026-10-25: migrations apply, 3 tenants seed, schema-bound JWT 401s cross-tenant, 34/34 tests pass, `check --deploy` has no security warnings, frontend builds |
| Brainstorming | Done | Scope agreed via client doc; design approved by owner 2026-10-25 |
| Strategy | Done | cto/eraj-v1.md, product-manager/eraj-v1.md |
| Design (ADRs) | Done | ADR-001 … ADR-006 |
| Planning | Done | engineering-manager/eraj-v1.md (M0–M8), senior-engineer/eraj-v1.md |
| Implementation | In progress | M0 started 2026-10-25 |

## Milestones
| ID | Due | Scope | State |
|---|---|---|---|
| M0 | 25 Oct | Dep fixes, Next upgrade, Refine shell builds | In progress |
| M1 | 27 Oct | org, people, RBAC, branch mixin, fresh migrations, staff shell | Not started |
| M2 | 30 Oct | Fees ledger, Library, Hostel + Mess + visitors | Not started |
| M3 | 2 Nov | Attendance, Exam, Timetable | Not started |
| M4 | 5 Nov | HR, Payroll | Not started |
| M5 | 7 Nov | Transport, Inventory | Not started |
| M6 | 9 Nov | Alerts, Portal, Learning | Not started |
| M7 | 10 Nov | Hindi pass, import templates, staging deploy | Not started |
| M8 | 11 Nov | Scenario run on staging, QA + security reports | Not started |
| Verification | Not started | |
| Delivery | Not started | |

## Known defects found in discovery
- `apps/fees` models drift from migration `0001` (`term`, `payer_reference`) — `makemigrations --check` fails
- `psycopg2-binary==2.9.9` fails to import on Python 3.13 (needs ≥2.9.10)
- Frontend: Next 14.2.35 — `npm audit`: 1 critical, 2 high
- `frontend/*.tsbuildinfo` not gitignored
