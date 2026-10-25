# Eraj — Project Status

**Phase:** Discovery Complete → Brainstorming (design approval pending)
**Updated:** 2026-10-25
**Target:** all modules running on staging by **2026-11-11** (owner on leave, full-time); client acceptance testing after that.
**Scope source:** `.10x/specs/2026-10-25-eraj-v1-scope.md` (summary of the client scope doc)

## Blockers
| # | Blocker | Owner | Needed by |
|---|---|---|---|
| B1 | Claude has no push access to `abhisheksinghs/eraj` — install the Claude GitHub App on the repo or reconnect GitHub in claude.ai settings | Abhishek | before first push (work continues locally until then) |
| B2 | Staging hosting account (DigitalOcean BLR1, or a VPS) + domain/DNS for `*.staging` subdomains | Abhishek | ~2026-11-05 |
| B3 | Branch model decision (tenant = organisation with branch rows, vs tenant = branch) | Abhishek | before Foundation work starts |

## Phase log
| Phase | State | Notes |
|---|---|---|
| Discovery | Done | Verified live on 2026-10-25: migrations apply, 3 tenants seed, schema-bound JWT 401s cross-tenant, 34/34 tests pass, `check --deploy` has no security warnings, frontend builds |
| Brainstorming | In progress | Scope agreed via client doc (11 modules + portal, alerts, branches, Hindi). Architecture design awaiting approval |
| Strategy | Not started | |
| Design (ADRs) | Not started | |
| Planning | Not started | |
| Implementation | Not started | |
| Verification | Not started | |
| Delivery | Not started | |

## Known defects found in discovery
- `apps/fees` models drift from migration `0001` (`term`, `payer_reference`) — `makemigrations --check` fails
- `psycopg2-binary==2.9.9` fails to import on Python 3.13 (needs ≥2.9.10)
- Frontend: Next 14.2.35 — `npm audit`: 1 critical, 2 high
- `frontend/*.tsbuildinfo` not gitignored
