# Handoff

**From:** M4 (2026-11-22) **To:** SDE — M5 (Transport, Inventory)

- M4 built, verified and pushed. ADR-009 (HR + payroll).
  - HR: profiles with payroll identity (restricted, masked), designations, documents, one-save staff
    attendance (+ punches), leave with reserved pending days, approve/reject/cancel, exit, register
    PDF, reports, self-service `/api/hr/me/*`. `staff_on_leave()` feeds timetable substitution.
  - Payroll: central + Bihar rule sets (matrix, DA history, HRA X/Y/Z, components), statutory
    settings (PF/EPS/NPS/ESI/PT/TDS as data), structures, pure `calc.py`, runs draft → review →
    locked with Admin reversal, increments, DA arrears with markers, loans, one-time payments,
    payslip PDF, bank sheet, register, ECR, ESIC, PT, 24Q, Form 16, statutory, YTD; own payslips.
- Verification: 165 Django + 26 pytest; walkthroughs (fresh `seed_demo_tenants` each):
  smoke-m1 14/14, m2-fees 19/19, m2-hostel 12/12, m3 14/14, m3-timetable 10/10, m4 20/20.
  Note: `next start` must be restarted (kill port 3000) after each `next build`.
- Waiting for M5: Inventory issue-to-staff from the shared staff list (HR-1 second half);
  hostel provisions + cost per head; GPS fake adapter.
- Client inputs needed (payroll): which staff on central vs Bihar rules; PF vs NPS per staff;
  actual DA %, HRA %, PT slabs, components; whether arrear PF goes in the month's ECR or a separate
  arrear ECR. Seeds carry sample values marked "(sample)".
- Blocker B2 (VPS + DNS) still open — staging deploy is M7.
- Commits: author Abhishek Singh, no AI attribution.
