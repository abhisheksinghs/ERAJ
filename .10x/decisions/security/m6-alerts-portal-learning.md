# Security — M6 Alerts, Portal, Learning (2026-11-22)

| Threat | Control | Evidence |
|---|---|---|
| Parent opens another child's records (IDOR) | every child route resolves through `access.child_for`: own student row or a student linked to a guardian with the caller's verified mobile, in the request's branch; anything else 404 (same as non-existent) | PORTAL-5 test, IDOR sweep over every child route × method, walkthrough (URL + `?child=`) |
| Phone enumeration via OTP request | identical response for known and unknown numbers; no OTP row for unknown numbers | test |
| OTP brute force | 6 digits, salted SHA-256 with SECRET_KEY, 5 minutes, 5 tries per code (saved before refusing), 3 codes per phone per 15 min, DRF `otp` scope 10/min per IP | tests (lockout, expiry, rate) |
| OTP readable by staff | code removed from the delivery log once sent; serializer masks it while queued; audit stores last 4 digits of the phone only | test + walkthrough |
| Staging code echo leaking to production | `PORTAL_OTP_ECHO=1` AND no enabled non-log-only channel for the branch; off by default | code review |
| Parent acting as the student (homework, tests, joins) | submit/start/finish/join require the student's own login | test (403) |
| Report card before publishing | portal lists/downloads published exams only; unpublished → 404 | PORTAL-3 test + walkthrough |
| Malicious uploads (homework, material) | extension allow-list + magic bytes + 10 MB; random stored names; served only via scoped endpoints with `nosniff` + attachment | tests |
| Teacher reading/grading other sections | queryset scoped by TeachingAssignment; create/update checked; Admin via `learning.all_sections` | test (404/409) |
| Test answers leaking | correct answers never sent before submission; shown after only if the teacher allows | test |
| Change request hijacking a login | applies only after office approval; audit trail; old number keeps only the children still on it | test |
| Forged delivery receipts | WhatsApp HMAC-SHA256 (app secret), SMS DLR token, both from env | notify tests |
| Provider credentials in the DB | only the env var *name* stored; UI shows whether it is set | design |
| Parent reaching staff APIs | parent/student roles hold `portal.*` only | test (403) |

Open: no CAPTCHA on OTP request (rate limits only) — revisit if abuse shows in audit logs; portal
sessions use the staff JWT lifetimes (15 min access / 1 day refresh) — consider a longer refresh
for parents after client feedback.
