# Handoff

**From:** M3 (2026-10-25) **To:** SDE — M4

- M2 and M3 built and pushed. ADRs 007 (hostel/mess/gate) and 008 (attendance/exam/timetable).
- M3: Attendance (one-save marking, daily/per-lecture, past corrections Admin-only + audit,
  holidays, register/daily/below-%/long-absent reports, ZKTeco-ADMS + JSON push + Excel/CSV punch
  import), Exam (scales/bands, exams with weightage, theory/practical, date sheet, subject-teacher
  marks grid, lock/unlock, computed results with competition ranks, analysis, annual weighting,
  SGPA/CGPA, report cards PDF), Timetable (bell schedules, rooms, teacher limits, clash-checked
  builder by time overlap, section/teacher/room views + PDF, substitution with ranked suggestions,
  register + PDF). Shared `people.TeachingAssignment`.
- Verification: 131 Django tests + 26 pytest; CI green; browser walkthroughs (each needs a fresh
  `seed_demo_tenants`): smoke-m1 14/14, smoke-m2-fees 19/19, smoke-m2-hostel 12/12,
  smoke-m3 14/14, smoke-m3-timetable 10/10.
- Hooks waiting for M4: `apps.timetable.services.absent_on()` imports `apps.hr.services.staff_on_leave`
  when it exists (approved HR leave → substitution list); staff `Punch` rows → HR attendance.
- Still open from M2: hand-built occupancy board / headcount / contractor-bill pages; Celery beat
  for `bill_mess_month` and `apply_late_fines`; provisions + cost/head (M5); real alerts (M6).
- M4 order: HR (profile, documents, departments/designations, staff attendance incl. punches,
  leave types/balances/approval, joining/exit, reports), then Payroll (central + Bihar pay rules,
  pay matrix, DA + arrears, PF/NPS/ESI/PT/TDS settings, LOP from HR, loans, run draft→review→lock,
  payslips, bank sheet, ECR/ESIC/PT/24Q data). ADR first.
- Commits: author Abhishek Singh, no AI attribution.
