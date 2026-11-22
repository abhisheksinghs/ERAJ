"""Files the accountant takes to the bank and the government portals (ADR-009).

Eraj prepares them; uploading and paying is done on the portals with the
institution's own logins (scope doc).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from apps.core.exceptions import Conflict
from apps.payroll.models import PayrollRun, Payslip, PayslipLine
from apps.payroll.services import add_months, fy_start, line_totals

ZERO = Decimal("0")


def _slips(run: PayrollRun):
    return run.payslips.select_related("staff__hr_profile", "staff__department").order_by("staff__employee_code")


def _int(x) -> int:
    return int(Decimal(x).quantize(Decimal("1")))


def bank_sheet(run: PayrollRun) -> list[dict]:
    rows = []
    for s in _slips(run):
        rows.append({"employee_code": s.staff.employee_code, "name": s.staff.full_name, "bank_account": s.bank_account,
                     "ifsc": s.ifsc, "net_pay": s.net_pay, "missing_bank_details": not (s.bank_account and s.ifsc)})
    return rows


def salary_register(run: PayrollRun) -> list[dict]:
    rows = []
    for s in _slips(run).prefetch_related("lines"):
        row = {"employee_code": s.staff.employee_code, "name": s.staff.full_name, "rule_set": s.rule_set_code,
               "level": s.level, "basic_full": s.basic_full, "da_percent": s.da_percent, "paid_days": s.paid_days,
               "lop_days": s.lop_days}
        for ln in s.lines.all():
            key = ln.code if not ln.code.startswith(("loan-", "once-")) else ("loan_recovery" if ln.code.startswith("loan-") else "one_time")
            row[key] = row.get(key, ZERO) + ln.amount
        row.update({"gross": s.gross, "total_deductions": s.total_deductions, "net_pay": s.net_pay})
        rows.append(row)
    return rows


def ecr_text(run: PayrollRun) -> str:
    """EPFO ECR 2.0: one line per member, fields separated by #~#:
    UAN, name, gross wages, EPF wages, EPS wages, EDLI wages, EPF (employee) contribution,
    EPS contribution, EPF–EPS difference (employer), NCP days, refund of advances."""
    slips = [s for s in _slips(run) if s.pf_wages or s.lines.filter(code="pf").exists()]
    missing = [s.staff.full_name for s in slips if not getattr(getattr(s.staff, "hr_profile", None), "uan", "")]
    if missing:
        raise Conflict("UAN missing for: " + ", ".join(missing) + ". Add it on the staff profile.")
    lines = []
    for s in slips:
        ee = PayslipLine.objects.filter(payslip=s, code="pf").aggregate(t=Sum("amount"))["t"] or ZERO
        name = " ".join(s.staff.full_name.upper().split())
        fields = [s.staff.hr_profile.uan, name, _int(s.gross), _int(s.pf_wages), _int(s.eps_wages), _int(s.eps_wages),
                  _int(ee), _int(s.employer_eps), _int(s.employer_epf), _int(s.lop_days), 0]
        lines.append("#~#".join(str(f) for f in fields))
    return "\n".join(lines) + ("\n" if lines else "")


def esic_sheet(run: PayrollRun) -> list[dict]:
    """ESIC monthly contribution upload: IP number, name, days paid, total wages, reason code, last working day."""
    rows = []
    for s in _slips(run):
        if not s.lines.filter(code="esi").exists():
            continue
        profile = getattr(s.staff, "hr_profile", None)
        relieved = profile.relieved_on if profile and profile.relieved_on and profile.relieved_on.replace(day=1) == run.month else None
        paid = _int(s.paid_days)
        rows.append({"ip_number": getattr(profile, "esic_ip", "") or "", "ip_name": s.staff.full_name,
                     "days_paid": paid, "total_monthly_wages": _int(s.gross),
                     "reason_code": "" if paid else "1", "last_working_day": relieved.strftime("%d/%m/%Y") if relieved else ""})
    return rows


def pt_register(run: PayrollRun) -> list[dict]:
    rows = []
    for s in _slips(run):
        pt = s.lines.filter(code="pt").aggregate(t=Sum("amount"))["t"] or ZERO
        rows.append({"employee_code": s.staff.employee_code, "name": s.staff.full_name, "gross": s.gross,
                     "professional_tax": pt})
    return rows


def _fy_slips(branch, fy: int):
    start = date(fy, 4, 1)
    return (Payslip.objects.filter(branch=branch, run__status=PayrollRun.Status.LOCKED, month__gte=start,
                                   month__lt=date(fy + 1, 4, 1))
            .select_related("staff__hr_profile").order_by("staff__employee_code", "month"))


QUARTERS = {1: (4, 5, 6), 2: (7, 8, 9), 3: (10, 11, 12), 4: (1, 2, 3)}


def tds_24q(branch, fy: int, quarter: int) -> list[dict]:
    """Deductee rows for the quarterly TDS return (Form 24Q, Annexure I)."""
    if quarter not in QUARTERS:
        raise Conflict("Quarter is 1 to 4 (Q1 = April–June).")
    rows = []
    for s in _fy_slips(branch, fy).filter(month__month__in=QUARTERS[quarter]):
        if not s.tds and not s.taxable_gross:
            continue
        rows.append({"pan": getattr(getattr(s.staff, "hr_profile", None), "pan", "") or "PANNOTAVBL",
                     "name": s.staff.full_name, "employee_code": s.staff.employee_code, "month": s.month.strftime("%Y-%m"),
                     "amount_paid": s.taxable_gross, "tds": s.tds, "date_of_payment": s.run.locked_at.date() if s.run.locked_at else ""})
    return rows


def form16(branch, fy: int) -> list[dict]:
    """Annual figures per staff member for Form 16 Part B."""
    per: dict[int, dict] = {}
    for s in _fy_slips(branch, fy):
        row = per.setdefault(s.staff_id, {
            "pan": getattr(getattr(s.staff, "hr_profile", None), "pan", "") or "PANNOTAVBL", "name": s.staff.full_name,
            "employee_code": s.staff.employee_code, "gross_salary": ZERO, "taxable_salary": ZERO,
            "tds_q1": ZERO, "tds_q2": ZERO, "tds_q3": ZERO, "tds_q4": ZERO, "tds_total": ZERO})
        q = next(k for k, v in QUARTERS.items() if s.month.month in v)
        row["gross_salary"] += s.gross
        row["taxable_salary"] += s.taxable_gross
        row[f"tds_q{q}"] += s.tds
        row["tds_total"] += s.tds
    return list(per.values())


def statutory_summary(branch, fy: int) -> list[dict]:
    rows = []
    m = date(fy, 4, 1)
    for _ in range(12):
        run = PayrollRun.objects.filter(branch=branch, month=m, status=PayrollRun.Status.LOCKED).first()
        if run:
            slips = run.payslips.all()
            t = line_totals(slips)
            agg = slips.aggregate(epf=Sum("employer_epf"), eps=Sum("employer_eps"), nps=Sum("employer_nps"),
                                  esi=Sum("employer_esi"))
            rows.append({"month": m.strftime("%Y-%m"), "pf_employee": t.get("pf", ZERO), "pf_employer_epf": agg["epf"] or ZERO,
                         "pf_employer_eps": agg["eps"] or ZERO, "nps_employee": t.get("nps", ZERO),
                         "nps_employer": agg["nps"] or ZERO, "esi_employee": t.get("esi", ZERO),
                         "esi_employer": agg["esi"] or ZERO, "professional_tax": t.get("pt", ZERO), "tds": t.get("tds", ZERO)})
        m = add_months(m, 1)
    return rows


def ytd(branch, fy: int, staff=None) -> list[dict]:
    slips = _fy_slips(branch, fy)
    if staff is not None:
        slips = slips.filter(staff=staff)
    per: dict[int, dict] = defaultdict(dict)
    names = {}
    for s in slips.prefetch_related("lines"):
        names[s.staff_id] = (s.staff.employee_code, s.staff.full_name)
        row = per[s.staff_id]
        row["months"] = row.get("months", 0) + 1
        for key, val in (("gross", s.gross), ("total_deductions", s.total_deductions), ("net_pay", s.net_pay), ("tds", s.tds)):
            row[key] = row.get(key, ZERO) + val
        for ln in s.lines.all():
            if ln.code in ("basic", "da", "hra", "da_arrears", "pf", "nps", "esi", "pt"):
                row[ln.code] = row.get(ln.code, ZERO) + ln.amount
    return [{"employee_code": names[k][0], "name": names[k][1], **v} for k, v in per.items()]


def current_fy(today: date) -> int:
    return fy_start(today.replace(day=1)).year
