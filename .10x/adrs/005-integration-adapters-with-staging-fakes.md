# ADR-005: External integrations behind adapters, with log-only fakes on staging

**Status:** Accepted
**Date:** 2026-10-25
**Feature:** eraj-v1
**Author:** 10x-Team (Architect + Staff Engineer)

## Context
SMS (DLT approval pending), WhatsApp (number available), email, GPS (provider unknown) and
biometric devices (several brands, unknown) all have external dependencies that will not all
be ready by 2026-11-11, but every acceptance scenario must be runnable on staging.

## Decision
- New tenant app `apps.integrations` with provider interfaces: `MessageChannel` (sms,
  whatsapp, email), `GpsSource`, `PunchSource`. Concrete providers are selected per branch in
  settings stored in the DB; credentials in env/secret store, never in the DB in plain text.
- `apps.notify` owns templates (en/hi), triggers, quiet hours, opt-outs and the delivery log.
  Sending happens in Celery tasks with retry; each attempt is logged with provider status.
- Every interface ships a `LogOnly` fake (records to the delivery log as `simulated`) and a
  `Simulated` GPS source for staging. Real providers: WhatsApp Cloud API + SMTP email first;
  SMS provider after DLT; GPS provider once named.
- Biometric: a generic authenticated push endpoint (device token per device) + Excel/CSV
  punch-log import. Brand-specific connectors are added per confirmed model.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Wait for providers before building | No fake code | Blocks scenarios; misses 11 Nov | Schedule |
| Hard-code one provider each | Less abstraction | Re-work when client picks differently (biometric brands vary) | Known variability |

## Consequences
### Positive
- Scenarios testable on staging; real providers drop in without touching modules.
### Negative
- Fake/real drift: a scenario passing on a fake does not prove the real provider works.
### Risks
- Staging shows `simulated` deliveries as success → the delivery log labels them clearly and
  the QA report lists which channels were real.

## Dependencies
- Constrains Attendance (punches), Transport (GPS), Portal (OTP), all alerting.
