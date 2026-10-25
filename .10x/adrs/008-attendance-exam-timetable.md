# ADR-008: Attendance with attendance devices, exam results, timetable and substitution

**Status:** Accepted
**Date:** 2026-10-25
**Feature:** eraj-v1 (M3)
**Author:** 10x-Team (Architect + DBA + Security + Senior Engineer)

## Context
Scope: Attendance (daily or per lecture, corrections, holidays, register/summary/below-%/long
absentee reports, biometric/RFID devices of several brands plus punch-log import), Exam (exams
with weightage, theory/practical, date sheet, marks grid restricted to the subject teacher, lock,
grade bands or SGPA/CGPA, ranks, per-exam and annual report cards, analysis) and Timetable (bell
schedule, teaching allocation, clash-checked builder, views, substitution with suggestions,
register). Attendance, Exam and Timetable all need "who teaches what to which section".

## Decision
**Shared: `people.TeachingAssignment`** (staff, subject, section, periods/week). Exam uses it for
"a subject teacher sees only their own subjects"; Timetable uses it as the allocation; Attendance
uses it (with `Section.class_teacher`) for which sections a teacher may mark. Admin-type roles hold
`attendance.record.any_section` / `exam.marks.all_subjects`; the teacher role is denied them.

**Attendance**
- `AttendanceSettings` per branch: mode `daily` | `per_lecture`, weekly offs (Sunday by default),
  below-threshold % (75), long-absence days (5). `Holiday` rows per branch.
- `AttendanceRecord` gains `section` (snapshot for fast reports) and `source` (`manual` | `device`).
- Marking: one save per section/date(/period): everyone present unless listed absent or given
  another status. Changing an existing mark on a past date needs `attendance.record.correct_past`
  (Admin); every change is written to the audit trail with old and new status.
- Percentage = (present + late + ½ half-day) ÷ marked working days. Holidays and weekly offs are
  not working days; a day nobody marked is left out (attendance was not taken).
- Devices (ADR-005 adapters): `AttendanceDevice` (brand, serial, token), `AttendanceCard`
  (card/user code → student or staff), `Punch` (deduplicated per branch + code + time).
  - ZKTeco ADMS push (`/iclock/cdata`, `/iclock/getrequest`) — also spoken by eSSL, Realtime and
    Identix devices, the common brands in Bihar; the device is identified by its registered
    serial number (devices cannot send our token) and must be active.
  - Generic JSON push `POST /api/attendance/push/` with `X-Device-Key` for any other device or
    vendor software that can call a URL.
  - Excel/CSV import of any device's punch log (code + date/time columns detected by header),
    validate-all-then-write like the student import.
  - In daily mode a student's first punch of the day marks them present at once (source
    `device`) unless a teacher already marked them; no punch leaves them unmarked for the teacher.
    In per-lecture mode punches only pre-fill the teacher's sheet. Staff punches are stored for HR
    attendance (M4).

**Exam**
- `GradeScale` (marks | credit) with `GradeBand` (grade, min %, grade point, fail flag).
- `Exam` (year, program, optional term, scale, weightage %, published flag) and `ExamSubject`
  (subject, theory/practical max, pass marks, date and time for the date sheet).
- `Mark` (exam subject, student, theory, practical, status present | absent | exempt).
  Absent shows as AB and counts 0 and fails the subject; exempt is left out of the maximum.
- `ExamLock` per exam + section: once locked only `exam.marks.unlock` (Admin) can unlock;
  locking and unlocking are audited.
- Results are computed, not stored: subject totals, total, %, grade, pass/fail, rank within
  section and within class (competition ranking: 1, 2, 2, 4).
- Annual result: per subject, Σ(exam % × weightage) ÷ Σ weightage over the chosen exams.
- SGPA = Σ(credits × grade point) ÷ Σ credits for one term's credit exam; CGPA over all terms.
- Report cards, class report cards (one PDF) and the date sheet print with WeasyPrint.

**Timetable**
- `BellSchedule` with `PeriodSlot`s (number, start, end, break flag, weekdays) — different
  schedules for different days or wings; each section uses one schedule.
- `Room`, `TeacherLoad` (max periods/week, default from settings).
- `TimetableEntry` (section, weekday, slot, teaching assignment, room). Refused when the section
  already has that slot, or the teacher or room is busy at an overlapping time that weekday (time
  overlap, so different bell schedules are compared correctly), or the teacher would exceed
  their weekly limit, or the assignment's periods/week are used up.
- Substitution for a date: the absent teacher's periods (from HR leave once M4 lands, or chosen
  by the office) are listed; candidates are teachers free at that time and not absent, ranked
  same subject first, then fewest periods that day. Confirming writes `Substitution`; the
  teacher view for that date and the register use it.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Store computed results | Fast reads | Stale after any mark change; lock semantics harder | Compute; class sizes are small |
| Per-brand SDK pull (ZK pull SDK over TCP 4370) | Works with old devices | Needs LAN access from the cloud | ADMS push + file import cover it |
| Auto-generate timetable | Less office work | Out of scope (scope doc) | Manual builder with clash checks |
| Lock per exam (all sections) | Simpler | Class teacher locks their own section | Lock per exam + section |

## Consequences
### Positive
- One allocation table drives exam permissions, timetable and attendance scope.
- Any device works: agreed brands live, everything else by file.
### Negative
- ADMS endpoints trust the device serial; production should also restrict by source IP
  (configurable allowlist per device).
- Brand list and models still to be confirmed with the client (open question in the scope doc).
