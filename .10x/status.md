# Eraj — Project Status

**Phase:** Implementation — M0–M6 done; M7 next
**Updated:** 2026-11-22
**Target:** all modules running on staging by **2026-11-11** (missed — work paused 25 Oct–22 Nov; new date to agree with owner) (owner on leave, full-time); client acceptance testing after that.
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
| Design (ADRs) | Done | ADR-001 … ADR-011 |
| Planning | Done | engineering-manager/eraj-v1.md (M0–M8), senior-engineer/eraj-v1.md |
| Implementation | In progress | M0–M3 done 2026-10-25; M4, M5, M6 done 2026-11-22; M7 next |
| Verification | Per milestone | QA/security notes per milestone in decisions/qa, decisions/security, reviews/ |
| Delivery | Not started | |

## Milestones
| ID | Due | Scope | State |
|---|---|---|---|
| M0 | 25 Oct | Dep fixes, Next upgrade, Refine shell builds | Done 25 Oct — Next 16.4.3 + React 19 + Refine 5/AntD 5 installed, `npm audit` 0, `next build` ok; psycopg2 2.9.13, WeasyPrint 70 (Hindi PDF verified), openpyxl |
| M1 | 27 Oct | org, people, RBAC, branch mixin, fresh migrations, staff shell | Done 25 Oct — backend 63 Django + 23 pytest green; frontend `next build` ok; browser walkthrough 14/14 (e2e/smoke-m1.mjs) |
| M2 | 30 Oct | Fees ledger, Library, Hostel + Mess + visitors | Built 25 Oct (ahead of 30 Oct) — 112 Django + 26 pytest green, CI green; walkthroughs M1 14/14, Fees 19/19, Hostel 12/12. Open: provisions + cost-per-head wait for Inventory (M5); parent alerts log-only until M6 |
| M3 | 2 Nov | Attendance, Exam, Timetable | Built 25 Oct (ahead of 2 Nov) — ADR-008; 131 Django + 26 pytest green; walkthroughs M3 14/14, Timetable 10/10 (all five e2e green). Open: device brands/models to confirm with client; HR leave → substitution list arrives with M4 |
| M4 | 5 Nov | HR, Payroll | Built 22 Nov — ADR-009; 165 Django + 26 pytest green; walkthroughs smoke-m4 20/20 and m1/m2/m3 all green; Next 16.4.6, npm audit 0. Open: inventory issue-to-staff (M5); client to confirm staff → rule set, PF vs NPS, real DA/HRA/PT/TDS values, arrear-ECR handling |
| M5 | 7 Nov | Transport, Inventory | Built 22 Nov — ADR-010; 182 Django tests green; walkthroughs smoke-m5 21/21 and m1–m4 all green; npm audit 0. Open: GPS provider name/API; real parent alerts (M6); X-Forwarded-For overwrite + positions retention + paper reminders on Celery beat (M7) |
| M6 | 9 Nov | Alerts, Portal, Learning | Built 22 Nov — ADR-011; 216 Django + 26 pytest green; walkthroughs smoke-m6 22/22 (phone viewport) and m1–m5 all green; npm audit 0. Open: DLT template ids + WhatsApp Business account (staging stays log-only); Celery worker + beat on staging (M7); OTP/positions retention jobs (M7) |
| M7 | 10 Nov | Hindi pass, import templates, staging deploy | Not started |
| M8 | 11 Nov | Scenario run on staging, QA + security reports | Not started |

## Known defects found in discovery
- ~~`apps/fees` models drift from migration `0001`~~ fixed M1 (migrations regenerated; drift check now blocking in CI)
- ~~CI red since 1 Sept: blocking ruff F401/F841 stopped the backend job before tests; test step skipped org/people/fees~~ fixed 25 Oct (`4ff2028`)
- ~~psycopg2 2.9.9 on Py 3.13~~ fixed M0 · ~~Next 14 advisories~~ fixed M0 · ~~tsbuildinfo~~ fixed M0
- ~~Django test modules collide in one invocation~~ fixed M1. Note: run module tests with `manage.py test` and the platform suite with `pytest` (pytest.ini pins `apps/core/tests`); mixing both in one pytest process leaks tenant state.
