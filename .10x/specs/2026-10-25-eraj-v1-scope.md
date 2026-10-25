# Eraj v1 — Scope (summary)

**Source of truth:** the client-facing scope document "Eraj v1 — Scope & Acceptance Criteria"
(claude.ai Docs artifact, https://claude.ai/artifact/T1VHY9A2SBiVNPTvsGF8Ss). Each module there
has features + numbered acceptance scenarios; this file is the engineering summary.

**Date:** 2026-10-25 · **Staging target:** 2026-11-11 (all modules) · **Payment:** on full acceptance

## Modules (11)
Library · Hostel and Mess (incl. visitors/outpass, contractor-run mess, monthly + per-day charging) ·
Attendance (daily or per-lecture; biometric/RFID multi-brand + punch-log import) · Fees (heads,
instalments, concessions, late fine, receipts, Tally export) · Exam (grade bands + SGPA/CGPA,
report cards) · HR (profile, documents, staff attendance, leave) · Payroll (central AND Bihar state
pay rules side by side, pay matrix, DA arrears, PF/NPS/ESI/PT/TDS, ECR/ESIC/24Q files) ·
Transport (routes, stop fees, vehicle docs, GPS) · Inventory (requisition → approval → PO → GRN) ·
Timetable and substitution · Homework and online learning

## Platform
Shared student/staff registry; configurable academic structure (school / college / coaching);
roles; dashboard; Excel/CSV/PDF exports; audit trail; multiple branches with group admin;
English + Hindi UI; parent & student portal (OTP login); alerts via SMS (DLT pending →
WhatsApp/email fallback), WhatsApp (Business number available), email.

## Out of scope
Online fee payment (not at launch) · native apps · admissions/enquiry · auto timetable
generation · built-in video · filing/paying on govt portals · live two-way Tally sync ·
supplying hardware or GPS subscriptions.

## Client answers so far
Institution type/size varies · both central and Bihar state pay rules · mess on campus by a
contractor, monthly and per-day charging · vehicles have GPS (provider TBC) · DLT in progress ·
WhatsApp Business number available · biometric brands vary · Hindi second language.

## Open with client
Branch count; board/university report format; sample receipt + fee structure; Tally version;
concession types; staff → rule set / PF vs NPS / TDS; mess rebate rule + contractor rates;
GPS provider + data access; DLT approval date; biometric brands/models; bilingual print;
data import formats; testers.

## Performance target (proposed, not yet agreed)
Counter/class screens < 2 s with 10,000 students and 500 staff in one branch.
