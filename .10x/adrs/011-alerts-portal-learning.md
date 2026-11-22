# ADR-011: Alerts with real channels, parent/student portal, homework and online learning

**Status:** Accepted
**Date:** 2026-11-22
**Feature:** eraj-v1 (M6)
**Author:** 10x-Team (Architect + DBA + Security + Senior Engineer)

## Context
Scope doc — Alerts: SMS (DLT pending → WhatsApp + email meanwhile), WhatsApp Business, email;
automatic alerts each switched on/off (absent, fee due/overdue, payment, results, homework, library
overdue, outpass, hostel out/in, bus near stop); manual notices to a class / section / route / hostel
block / all parents / all staff; en + hi templates; quiet hours; opt-out per parent and channel;
delivery log with provider reason and monthly counts. Scenarios ALR-1…4.
Portal: parent OTP login on the registered mobile, one login for all their children; student
logins for chosen classes; per-child home, attendance, fees + receipts, published report cards,
timetable with substitutions, homework/material (students submit), hostel outpass + mess menu,
transport + live bus, notices with read status, day-scholar leave to the class teacher, change
requests approved by the office. Scenarios PORTAL-1…5 (incl. no access to another child by URL).
Learning: homework with attachments, submissions (text/photo/file), grading, late flag; material
by class/subject/chapter; online classes with join record; MCQ tests with time limit and automatic
marking; class diary; reports. Scenarios LRN-1…4.
Every module already calls `apps.core.notify.guardian()` / `staff_role()` (log-only, ADR-005).

## Decision

### Alerts (`apps.notify`, tenant app)
- `ChannelConfig` per branch × channel (sms / whatsapp / email): provider `log_only` | `sms_http`
  (DLT gateway URL template) | `whatsapp_cloud` (Meta Cloud API) | `smtp`; sender (DLT header,
  phone-number id, from address); **credentials are named env vars**, never stored in the DB.
  SMS stays disabled until DLT approval; events then go by WhatsApp + email (scope).
- `AlertRule` per branch × event (on/off, channels). Event catalogue in code with en/hi default
  texts; `Template` rows override per event × channel × language (+ DLT / WhatsApp template id).
- `NotifySettings`: quiet hours (21:00–07:00 default). `OptOut` per guardian × channel.
- `Message` is the delivery log: event, channel, recipient, body, status queued → sent →
  delivered | failed (provider reason) | held (quiet hours, `send_after`) | simulated (log_only) |
  skipped (opted out / no contact), provider ref, attempts. Monthly counts per channel come from it.
- `raise_event(branch, event, recipients, context)` writes the rows and, on commit, queues a
  Celery task per message (`send_message(schema, id)`, retries with back-off). Celery beat:
  release held messages every 5 min; daily fee due/overdue reminders.
- WhatsApp delivery receipts: `POST /api/notify/webhooks/whatsapp/` verified with
  `X-Hub-Signature-256` (HMAC of the body with the app secret env var); GET verify-token handshake.
- `core.notify.guardian()` / `staff_role()` keep their signatures and now call `raise_event`, so
  every existing module alert is real. Attendance raises `attendance.absent` once per student/day.
- `Notice`: audience = section | program | route | hostel block | all parents | all staff;
  sent through `raise_event` and shown on the portal with `NoticeRead` receipts.
- Staging uses `log_only` (status `simulated`, clearly labelled); WhatsApp and SMTP are real
  adapters exercised against a stubbed HTTP/SMTP layer in tests.

### Portal (`apps.portal`)
- OTP: `PortalOTP` stores a salted hash of a 6-digit code, 5-minute expiry, 5 attempts; at most
  3 codes per phone per 15 minutes; the request endpoint always answers the same way (no phone
  enumeration). The code goes by SMS, else WhatsApp, ignoring quiet hours and opt-outs.
- On verify, the guardian gets (or keeps) a `User` (synthetic unique email, unusable password,
  phone set) linked to `Guardian.user` and a `parent` role in each branch of their children; the
  usual schema-bound JWT pair is returned (ADR-004 cookies on the frontend).
- Students: office creates a login per student (email + password) → `student` role.
- Every child endpoint resolves the child through `portal.access.child_for(request, id)`: the
  caller's own student row, or a student linked to the caller's guardian row — anything else is
  404 (PORTAL-5). No staff serializers are reused for writes; portal serializers are read-mostly.
- `ChangeRequest` (address / phone / email → office approves, then applied) and `StudentLeave`
  (day scholar → class teacher approves; approved days pre-mark attendance as leave).

### Learning (`apps.learning`)
- `Homework` (section, subject, teacher, due) + `HomeworkFile`; `Submission` (+ files, `late`
  computed at submit, grade + remarks); `Material` (program/section, subject, chapter, file or link);
  `OnlineClass` (section, subject, start/end, link) + `JoinRecord` (first open per student);
  `OnlineTest` (opens/closes, time limit) + `Question` (MCQ, options, correct index, marks) +
  `Attempt` (deadline = start + limit, answers, auto score); `DiaryEntry` (section, date, period,
  subject, topic). Teachers act only on their own teaching assignments (as Exam marks, ADR-008);
  Admin on all. Files: same checks as HR documents (type allow-list, magic bytes, size), private
  download through the API.
- Online classes appear in the section timetable for their date and on the portal.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Send synchronously in the request | Simple | Slow requests; provider outage breaks marking attendance | Celery + log |
| Third-party notification SaaS | Less code | Another processor of children's data (DPDP), cost | Own log + thin adapters |
| Separate portal frontend app | Isolation | Second deploy, duplicate auth | Same Next app, separate layout + role |
| Parent login with password | Familiar | Scope says OTP; parents forget passwords | OTP |
| Store tokens/creds in DB encrypted | One place | Key management; scope ADR-005 says env | Env var names |

## Consequences
### Positive
- Every existing alert call site becomes a real, logged, opt-out-aware message with no change to
  the modules; scenarios testable on staging with log_only.
### Negative
- Real delivery depends on DLT approval and a WhatsApp Business template approval (client side).
- OTP cost per login (SMS/WhatsApp) is paid by the institution.
### Risks
- OTP brute force → hashed codes, attempts cap, send rate cap, IP throttle.
- Child IDOR → single `child_for` gate + tests that try other ids on every endpoint.

## Dependencies
- ADR-001…010. Constrains M7 (Celery worker + beat in deploy; env vars for providers).
