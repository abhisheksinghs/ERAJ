# CTO — eraj-v1

**Date:** 2026-10-25

## Decision: build (not buy), on the existing Eraj codebase
- Client requires all 11 modules + portal/alerts/branches/Hindi; payment only on full acceptance.
- Existing backend is sound (verified live: isolation, auth, state machine); reuse it.
- Off-the-shelf school ERPs could meet a near date faster, but Eraj is the owner's product and
  this client is its first; building it is the strategy.

## Constraints accepted
- Staging with all modules by 2026-11-11 (owner full-time on leave + AI-assisted build).
- Full scope estimated ~49 weeks part-time; compressing to 17 days full-time means first-pass
  depth on staging, then acceptance testing. Risk accepted by the owner on 2026-10-25.

## Tech direction
Django 5 + django-tenants + DRF (keep) · Next.js (upgrade) + Refine + Ant Design (ADR-004) ·
Postgres 16 · Redis + Celery · WeasyPrint PDFs · openpyxl exports · India-region hosting.

## Commercial risk (owner's call, recorded)
No payment until full acceptance; recommended staged payments. Not resolved.
