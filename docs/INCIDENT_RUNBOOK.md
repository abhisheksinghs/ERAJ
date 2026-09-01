# Eraj — Incident Runbook

## Severity

| Sev | Meaning | Example |
|---|---|---|
| **SEV1** | Data exposed across tenants, or platform down for all | a token authenticates against the wrong tenant; DB unreachable |
| **SEV2** | One tenant down, or auth broken | a schema's migrations half-applied; login 500s |
| **SEV3** | Degraded, no data risk | Celery backlog; elevated p99 |
| **SEV4** | Cosmetic / single-user | one stale cache entry |

## First response (any sev)

1. **Declare** — post in the incident channel with sev + one-line summary.
   One person is Incident Commander.
2. **Stop the bleeding before diagnosing.** For a suspected cross-tenant data
   issue (SEV1): put the app in maintenance (scale `web` to 0 or a static
   holding page) *first*, investigate second.
3. **Capture evidence** — `AuditLog` rows for the window
   (`SELECT * FROM public.core_auditlog WHERE at > ... ORDER BY at`), app logs
   (filter by `schema`), Sentry issue link, DB slow-query log.
4. **Timeline** — keep a running note: what was seen, when, what was changed.

## Common failures → action

| Symptom | Likely cause | Action |
|---|---|---|
| Queries return another tenant's rows | pooler in `transaction` mode | switch pool to `session` mode; rotate the pool; audit affected window |
| One tenant 500s everywhere | migrations half-applied to that schema | re-run `migrate_schemas -s <schema>`; check the PRE_DEPLOY job log |
| All API calls 402 | `Subscription` recompute bug or cache poisoning | `cache.clear()`; inspect the row; check the daily task's last run |
| Login 401 for valid creds | `schema` claim vs resolved schema mismatch | check `Domain` table + subdomain; check `TenantBoundJWTAuthentication` |
| Celery not processing | broker down / beat duplicated / worker OOM | check Redis; confirm exactly one `celery-beat`; check `worker_max_tasks_per_child` |

## DPDP breach path (personal data exposed or at risk)

Trigger: any SEV1 involving student/staff personal data, or credible evidence
of unauthorized access.

1. Contain (above) and preserve logs — do not delete anything.
2. Assess scope: which tenants, which data categories, how many principals,
   window of exposure (use `AuditLog` + DB timestamps).
3. **Notify the Data Protection Board of India and affected Data Fiduciaries
   (the institutions) without undue delay.** Institutions notify their own
   data principals; give them the facts to do so.
4. Post-incident review within 5 working days — see below. Share remediation
   with affected institutions.

## Post-incident review (blameless)

Within 5 working days: timeline, root cause (5 whys), what detection/response
worked and didn't, concrete action items with owners and dates. File it in
`docs/` and link it from `FAILURE_MODES.md` if it's a new failure mode.
