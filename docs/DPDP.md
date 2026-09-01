# Eraj — Data Protection (India DPDP Act, 2023)

Roles: the **institution is the Data Fiduciary**, Eraj is the **Data
Processor**. Eraj processes personal data only on documented instructions from
the institution (the DPA).

## Data map

| Data | Where | Category | Retention |
|---|---|---|---|
| Staff/owner accounts (email, name, password hash, role) | tenant schema `accounts_user` | contact + credential | life of the contract + 30 days |
| Library members (name, email) | tenant schema `library_member` | contact | per institution instruction; default = life of contract |
| Hostel residents (name) | tenant schema `hostel_resident` | contact | as above |
| Superadmin accounts | `public.accounts_user` | contact + credential | life of employment |
| Audit log (actor email, action, tenant) | `public.core_auditlog` | activity | 1 year |
| Tenant/plan/subscription | `public.core_*` | commercial, minimal PII | life of contract + 7 years (tax) |

**Minors:** some library members / residents may be under 18. Institutions are
responsible for verifiable parental consent; Eraj does not process children's
data for tracking, advertising, or profiling.

## Localization

All infrastructure (App Platform, Managed Postgres, Managed Redis) is in an
India region (BLR1). No sub-processor may move personal data out of India
without an amended DPA.

## Sub-processors

| Sub-processor | Purpose | DPA |
|---|---|---|
| DigitalOcean | hosting, DB, Redis | required before go-live |
| Sentry | error tracking (`send_default_pii=False`) | required before go-live |
| (email provider — TBD) | password-reset + transactional mail | required before go-live |

Changes to this list are notified to institutions before taking effect.

## Rights of data principals

Requests come *through the institution* (the Fiduciary), not directly to Eraj.

- **Access / correction** — via the app (staff edit `library_member` etc.);
  account holders use `PATCH /api/auth/me/`.
- **Erasure of one principal** — delete the row(s); FK `PROTECT` on
  `library_issue` means outstanding loans must be closed first. Log the action
  in `AuditLog`.
- **Erasure of a whole institution (offboarding)** — export
  (`pg_dump -n <schema>`), deliver to the institution, then `drop_schema`. The
  schema-per-tenant model makes this a clean, complete deletion.

## Breach notification

See `docs/INCIDENT_RUNBOOK.md` → "DPDP breach path". Notify the Data Protection
Board and affected Fiduciaries without undue delay; preserve `AuditLog` and
application logs as evidence.

## Team access to production

Least-privilege, MFA on every account, a logged break-glass procedure for
emergencies, and a quarterly access review. No standing direct DB access —
use `doctl apps run` with an audited command.
