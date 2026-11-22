# Handoff

**From:** M6 (2026-11-22) **To:** DevOps + SDE — M7 (Hindi pass, import templates, staging deploy)

- M6 built, verified and pushed. ADR-011.
  - Alerts (`apps.notify`): rules, en/hi templates, SMS / WhatsApp / email adapters (+ log-only),
    quiet hours, opt-out, delivery log with receipts, monthly counts, notices with read status.
    `core.notify.guardian/staff_role/staff_users` raise real events everywhere.
  - Learning (`apps.learning`): homework + files + grading, material, online classes (timetable +
    join record), MCQ tests, class diary, reports; teachers limited to their own sections.
  - Portal (`apps.portal` + `/portal`): parent OTP login (one login across branches), student
    logins, child gate (`access.child_for`), 12 phone-first sections, leave + change requests.
- Verification: see status.md (Django suite, smoke-m6 22/22, m1–m5 green, npm audit 0).
  Walkthrough needs Django started with `PORTAL_OTP_ECHO=1` and a Celery worker
  (`celery -A config worker`), fresh `seed_demo_tenants` each run, `next start` restarted per build.
- For M7 deploy:
  - Run **Celery worker + beat** (beat: `notify-release-held` every 5 min — also re-queues stuck
    messages; `notify-daily-reminders` 09:00). Without a worker, alerts stay "queued".
  - `kombu==5.4.2` is now pinned (5.5+ breaks with redis-py 5.0.8).
  - Env: `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `SMS_DLR_TOKEN`, provider keys named in
    each channel's "credential env" field; `EMAIL_*`. Never set `PORTAL_OTP_ECHO` in production.
  - Reverse proxy must **overwrite** `X-Forwarded-For` (GPS/attendance allow-lists).
  - Retention jobs: VehiclePosition 90 days, PortalOTP 1 day.
  - Hindi pass: portal strings are inline in `components/portal/*` (t(en, hi)); review with the
    client's Hindi reviewer along with lib/resources.ts.
- Client inputs still open: DLT registration + template ids; WhatsApp Business number; GPS
  provider; staff → pay rule set / PF vs NPS; biometric models.
- Blocker B2 (VPS + DNS) still open.
- Commits: author Abhishek Singh, no AI attribution.
