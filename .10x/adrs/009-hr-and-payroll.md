# ADR-009: HR records, staff attendance and leave; payroll with two government rule sets

**Status:** Accepted
**Date:** 2026-11-22
**Feature:** eraj-v1 (M4)
**Author:** 10x-Team (Architect + DBA + Security + Senior Engineer)

## Context
Scope doc, HR: staff profile (incl. bank and identity details for payroll), documents,
departments and designations, staff attendance (present / absent / leave / half-day / on duty)
with a monthly register, leave types with yearly entitlement, apply → approve/reject with
automatic balances, joining and exit, reports. Scenarios HR-1…4.

Payroll: central AND Bihar state rule sets side by side, each with its own pay matrix, DA rate and
allowances; each staff member on one. Basic from the matrix, DA % of basic, HRA by city class,
other allowances fixed or % of basic, annual increment to the next matrix cell, DA arrears when DA
is revised from a past date. PF or NPS, ESI, PT, TDS switchable per staff member, with rates,
ceilings and slabs as settings. Loss of pay from HR, loans/advances, draft → review → lock with
Admin-only reversal, one-time payments, payslip PDFs, bank sheet, reports, and ECR / ESIC / PT /
24Q / Form 16 data. Scenarios PAY-1…8.

Client answers: both rule sets apply; which staff are on which rule set and PF vs NPS is still
open — so every rate and slab must be data, and the code ships sample configs only.

## Decision

### HR (`apps.hr`)
- `StaffProfile` 1:1 with `people.Staff` (ADR-002 registry stays the identity): gender, father/
  spouse, address, qualifications, experience, probation end, relieving date + exit reason, and
  payroll identity: PAN, UAN, ESIC IP no., PRAN, bank name, account no., IFSC. No Aadhaar number
  is stored (nothing in payroll needs it). Profile endpoints need `hr.profile.view` — HR, Admin,
  Accountant only; account numbers are masked in list responses.
- `Designation` master per branch; `Staff.designation` keeps the name (picked from the master in
  the UI) so existing modules are untouched.
- `StaffDocument`: file per staff member; PDF/JPG/PNG only, ≤ 5 MB, stored under a random name,
  downloaded only through an authenticated endpoint (never a public media URL).
- `StaffAttendance` (staff, date, status present | absent | leave | half_day | on_duty, source
  manual | device | leave, leave application, unpaid flag). One save per date marks everyone
  present unless listed otherwise (same as students, ADR-008). Staff punches (ADR-008) mark
  present on the first punch of the day unless already marked. Weekly offs and holidays reuse
  `attendance.AttendanceSettings` / `attendance.Holiday` of the branch.
- Leave: `LeaveType` (code, annual days, paid, half-day allowed; unpaid type has no limit),
  `LeaveBalance` (staff, type, leave year = calendar year, entitled incl. carried forward, used),
  `LeaveApplication` (pending → approved | rejected | cancelled). Days exclude weekly offs and
  holidays. **Available = entitled − used − pending**, so two pending applications cannot
  overspend. Approval re-checks under `select_for_update`, adds to `used`, and writes
  `StaffAttendance` rows (status leave, unpaid for an unpaid type) for each working day.
  Cancelling an approved leave reverses both. `hr.services.staff_on_leave()` feeds the timetable
  substitution list (hook already in `apps.timetable.services.absent_on`).
- Exit: `exit_staff` sets `Staff.status = left` and the relieving date/reason, cancels pending
  leave; the staff list API returns active staff unless `?status=` is given, so left staff vanish
  from active lists and stay in history.
- Self-service: any staff user linked to a `Staff` row can see their own balances, apply for and
  cancel their own pending leave, and download their own payslips (`hr.self.*`,
  `payroll.self.view`).

### Payroll (`apps.payroll`, replaces the flat M0 `Payslip`)
- **Rule set** `PayRuleSet` (branch, code, name: e.g. "Central 7th CPC", "Bihar 7th CPC") holds:
  `PayLevel` → `PayCell` (index, basic) = the pay matrix; `DARate` history (effective from, %);
  HRA % for city classes X / Y / Z; `PayComponent`s (earning or deduction; fixed amount or % of
  basic; taxable flag) with optional per-staff amount override.
- `SalaryStructure` per staff: rule set + level + cell index → basic (or a fixed basic for
  contract staff), city class, increment month (Jan or Jul), switches PF / NPS (mutually
  exclusive) / ESI / PT / TDS, optional fixed monthly TDS (staff on the old regime).
- `StatutorySettings` per branch: PF employee %, EPS %, PF wage ceiling + "cap wages" flag; NPS
  employee / employer %; ESI employee / employer % + wage ceiling; PT monthly slab table; TDS
  slabs, standard deduction, rebate limit, cess %. All entered by the accountant; seeds carry
  sample values only.
- Calculation per staff per month (whole rupees, half-up; ESI rounded up as ESIC does):
  - days = calendar days of the month; LOP days = absent + unpaid leave + ½ × half-day from
    `StaffAttendance` (unmarked days are not LOP); paid days = days − LOP.
  - Every earning × paid days ÷ days. DA = basic × DA % (rate in force on the 1st of the month).
    HRA = basic × city-class %.
  - PF: 12 % of (basic + DA) earned, capped at the ceiling when set; employer EPS 8.33 % of
    min(wages, ceiling), EPF = employer 12 % − EPS. NPS: employee % and employer % of (basic + DA).
    ESI: when gross ≤ ceiling. PT: slab on gross. TDS: fixed amount if set, else (projected
    annual tax by slabs − TDS already deducted this financial year) ÷ months left.
  - Loan/advance recovery = min(monthly recovery, balance); balance falls when the month locks.
  - One-time payments (bonus, increment arrears, other) for that month are added as earnings.
- **Runs** `PayrollRun` (branch, month): draft (recompute freely) → review (figures frozen; back
  to draft or lock) → locked. Locked: no recompute, no attendance/leave/one-time-payment change
  for that month (409). Reversal: Admin only (`payroll.run.reverse`), reason required, audited,
  restores loan balances and arrear markers; the month can then be run again.
  `Payslip` + `PayslipLine` are snapshots (rule set, level, basic, DA %, days, LOP) so a later
  structure change never alters a locked month.
- **DA arrears**: revising DA writes a `DARate` with a past effective date. The next run's
  calculation compares, for every locked payslip on or after that date in the same rule set, the
  DA paid (payslip DA % + arrears already paid) with the rate now in force, and adds the
  difference (× that month's paid days) as a "DA arrears" earning, with PF/NPS on it. `ArrearPayment`
  rows record source payslip → paying payslip, so nothing is paid twice and reversal is exact.
  Revising one rule set never touches staff on the other (PAY-8).
- **Increments**: creating a run applies due increments (structure's increment month = run month,
  not yet applied this year) by moving to the next matrix cell; each is audited and listed on the
  run.
- **Outputs**: payslip PDF (one / whole run, WeasyPrint, amount in words), bank sheet, salary
  register, statutory summary, YTD, ECR text file (EPFO ECR 2.0, `#~#` separated, UAN required),
  ESIC monthly contribution sheet, PT register, quarterly 24Q deductee data, Form 16 annual data.
  Eraj produces files; the accountant uploads and pays on the portals (scope doc).

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| One generic formula engine (expressions per component) | Any rule expressible | Untestable configs, accountant can't own it, injection risk | Typed components + settings cover both rule sets |
| Rule sets shared across branches (client-wide) | No duplication for a trust | Breaks ADR-001 (all data branch-owned), scope rules differ by branch | Branch-owned; copy-from-branch later if needed |
| Store only payslip totals | Simpler | Arrears / reports / ECR need component detail | Lines + snapshot fields |
| Recompute arrears from structures | No marker table | Double payment on re-run; reversal ambiguous | `ArrearPayment` markers |
| LOP as a separate deduction line | Visible | Govt practice prorates earnings; PF base must be earned wages anyway | Prorate earnings; payslip shows LOP days |
| Leave balance = entitled − used (ignore pending) | Simpler | Two pending applications overspend | Reserve pending |

## Consequences
### Positive
- Both government rule sets are configuration; DA revisions and arrears are one action.
- Locked months are immutable snapshots; reversal is the only way back and is audited.
- Timetable substitution gets HR leave automatically.
### Negative
- TDS projection is the new-regime slab method; old-regime staff need the fixed monthly figure.
- ECR acceptance and figure-matching (PAY-5, PAY-6) can only be signed off by the client's
  accountant on real data; tests check format and arithmetic.
- Arrear PF/NPS is deducted in the paying month and included in that month's ECR wages
  (accountant to confirm; separate arrear ECR not built).
### Risks
- Staff → rule set / PF vs NPS mapping unknown (scope open item) — sample configs, client fills.
- PAN / UAN / bank numbers are sensitive: restricted permission, masked lists, no Aadhaar.

## Dependencies
- ADR-001 (branch rows), ADR-002 (people registry), ADR-006 (RBAC), ADR-008 (punches, holidays,
  `absent_on` hook).
