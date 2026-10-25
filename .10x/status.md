# Eraj — Project Status

**Phase:** Implementation — M0, M1 done; M2 next
**Updated:** 2026-10-25
**Target:** all modules running on staging by **2026-11-11** (owner on leave, full-time); client acceptance testing after that.
**Scope source:** `.10x/specs/2026-10-25-eraj-v1-scope.md` (summary of the client scope doc)

## Blockers
| # | Blocker | Owner | Needed by |
|---|---|---|---|
| ~~B1~~ | ~~Push access~~ — GitHub connected by owner 2026-10-25 | — | — |
| B2 | VPS (India, 4 GB / 2 vCPU, Ubuntu LTS) + SSH access; DNS A records `eraj.abhisheksingh.in` and `*.eraj.abhisheksingh.in` → VPS IP (domain decided 2026-10-25, see devops/eraj-v1.md) | Abhishek | ~2026-11-03 |
| ~~B3~~ | ~~Branch model decision~~ — resolved 2026-10-25: branch rows inside client schema (ADR-001) | — | — |

## Phase log
| Phase | State | Notes |
|---|---|---|
| Discovery | Done | Verified live on 2026-10-25: migrations apply, 3 tenants seed, schema-bound JWT 401s cross-tenant, 34/34 tests pass, `check --deploy` has no security warnings, frontend builds |
| Brainstorming | Done | Scope agreed via client doc; design approved by owner 2026-10-25 |
| Strategy | Done | cto/eraj-v1.md, product-manager/eraj-v1.md |
| Design (ADRs) | Done | ADR-001 … ADR-006 |
| Planning | Done | engineering-manager/eraj-v1.md (M0–M8), senior-engineer/eraj-v1.md |
| Implementation | In progress | M0, M1 done 2026-10-25; M2 next |
| Verification | Not started | |
| Delivery | Not started | |

## Milestones
| ID | Due | Scope | State |
|---|---|---|---|
| M0 | 25 Oct | Dep fixes, Next upgrade, Refine shell builds | Done 25 Oct — Next 16.4.3 + React 19 + Refine 5/AntD 5 installed, `npm audit` 0, `next build` ok; psycopg2 2.9.13, WeasyPrint 70 (Hindi PDF verified), openpyxl |
| M1 | 27 Oct | org, people, RBAC, branch mixin, fresh migrations, staff shell | Done 25 Oct — backend 63 Django + 23 pytest green; frontend `next build` ok; browser walkthrough 14/14 (e2e/smoke-m1.mjs) |
| M2 | 30 Oct | Fees ledger, Library, Hostel + Mess + visitors | Next |
| M3 | 2 Nov | Attendance, Exam, Timetable | Not started |
| M4 | 5 Nov | HR, Payroll | Not started |
| M5 | 7 Nov | Transport, Inventory | Not started |
| M6 | 9 Nov | Alerts, Portal, Learning | Not started |
| M7 | 10 Nov | Hindi pass, import templates, staging deploy | Not started |
| M8 | 11 Nov | Scenario run on staging, QA + security reports | Not started |

## Known defects found in discovery
- `apps/fees` models drift from migration `0001` (`term`, `payer_reference`) — `makemigrations --check` fails
- ~~psycopg2 2.9.9 on Py 3.13~~ fixed M0 · ~~Next 14 advisories~~ fixed M0 · ~~tsbuildinfo~~ fixed M0
- Test suites pass per module (17/17) but error when Django test modules run in one invocation: public-schema `Module`/`Client` fixtures collide (`core_module_code_key`). Pre-existing; fix in M1 fixture rework.
