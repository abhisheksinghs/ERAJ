"""Payroll run lifecycle, increments, DA arrears and loan recovery (ADR-009).

    run = create_run(branch=b, month=date(2026, 11, 1), by="acct@x")   # draft, computed
    submit(run=run, by=…); lock(run=run, by=…)                          # review → locked
    reverse(run=run, reason="wrong DA", by="admin@x")                   # Admin only
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.payroll import calc
from apps.payroll.models import (
    ArrearPayment, DARate, Loan, LoanRecovery, OneTimePayment, PayCell, PayComponent, PayrollRun, Payslip, PayslipLine,
    SalaryStructure, StatutorySettings,
)
from apps.people.models import Staff

ZERO = Decimal("0")
RUN = PayrollRun.Status


# ------------------------------------------------------------------ helpers
def first_of(d: date) -> date:
    return d.replace(day=1)


def last_of(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def fy_start(month: date) -> date:
    return date(month.year if month.month >= 4 else month.year - 1, 4, 1)


def months_left_in_fy(month: date) -> int:
    end = date(fy_start(month).year + 1, 3, 1)
    return (end.year - month.year) * 12 + end.month - month.month + 1


def locked_months(*, branch, months) -> set[date]:
    months = {first_of(m) for m in months}
    if not months:
        return set()
    return set(PayrollRun.objects.filter(branch=branch, month__in=months, status=RUN.LOCKED).values_list("month", flat=True))


def guard_month_open(*, branch, month: date) -> None:
    if locked_months(branch=branch, months=[month]):
        raise Conflict(f"Payroll for {month:%B %Y} is locked; it can't be changed. Admin can reverse the run.")


def statutory_for(branch) -> StatutorySettings:
    obj, _ = StatutorySettings.objects.get_or_create(branch=branch)
    return obj


def statutory_input(st: StatutorySettings) -> calc.Statutory:
    return calc.Statutory(
        pf_employee_percent=st.pf_employee_percent, pf_employer_percent=st.pf_employer_percent,
        eps_percent=st.eps_percent, pf_wage_ceiling=st.pf_wage_ceiling, pf_cap_wages=st.pf_cap_wages,
        nps_employee_percent=st.nps_employee_percent, esi_employee_percent=st.esi_employee_percent,
        esi_employer_percent=st.esi_employer_percent, esi_wage_ceiling=st.esi_wage_ceiling,
        pt_slabs=st.pt_slabs or [], tds_slabs=st.tds_slabs or [], tds_standard_deduction=st.tds_standard_deduction,
        tds_rebate_limit=st.tds_rebate_limit, tds_cess_percent=st.tds_cess_percent,
    )


def da_percent_on(rule_set, month: date) -> Decimal:
    rate = DARate.objects.filter(rule_set=rule_set, effective_from__lte=first_of(month)).order_by("-effective_from").first()
    return rate.percent if rate else ZERO


def basic_of(structure: SalaryStructure) -> Decimal:
    if structure.fixed_basic is not None:
        return structure.fixed_basic
    cell = PayCell.objects.filter(level=structure.level, index=structure.cell_index).first()
    if cell is None:
        raise Conflict(f"Level {structure.level.code} has no cell {structure.cell_index}.")
    return cell.basic


def _pct(x) -> str:
    return f"{Decimal(x).normalize():f}"


# ------------------------------------------------------------------ increments
def apply_increments(*, branch, month: date, by: str) -> list[str]:
    """Move each due structure to the next cell of its level (6 months' service
    by the increment date). Already applied this year → skipped."""
    notes = []
    six_months_before = add_months(month, -6)
    qs = (SalaryStructure.objects.select_for_update().select_related("staff", "level")
          .filter(branch=branch, is_active=True, increment_month=month.month, level__isnull=False,
                  staff__status=Staff.Status.ACTIVE))
    for s in qs:
        if s.last_increment_on and s.last_increment_on.year == month.year and s.last_increment_on.month == month.month:
            continue
        if s.staff.date_joined > six_months_before:
            notes.append(f"{s.staff.full_name}: increment not due (less than 6 months' service)")
            continue
        nxt = PayCell.objects.filter(level=s.level, index=s.cell_index + 1).first()
        if nxt is None:
            notes.append(f"{s.staff.full_name}: already at the last cell of level {s.level.code}")
            continue
        old = s.cell_index
        s.cell_index, s.last_increment_on = nxt.index, month
        s.save(update_fields=["cell_index", "last_increment_on", "updated_at"])
        record("payroll.increment", actor=by, staff=s.staff_id, level=s.level.code, cell_from=old, cell_to=nxt.index,
               month=str(month))
        notes.append(f"{s.staff.full_name}: increment, level {s.level.code} cell {old} → {nxt.index} (₹{nxt.basic})")
    return notes


# ------------------------------------------------------------------ arrears
def _paid_percent(slip: Payslip) -> Decimal:
    latest = (ArrearPayment.objects.filter(source=slip, paid_in__run__status=RUN.LOCKED)
              .order_by("-to_percent").values_list("to_percent", flat=True).first())
    return latest if latest is not None else slip.da_percent


def due_arrears(*, staff, rule_set, before: date) -> list[dict]:
    """DA still owed on earlier locked payslips of this rule set (ADR-009)."""
    out = []
    for slip in (Payslip.objects.filter(staff=staff, rule_set=rule_set, run__status=RUN.LOCKED, month__lt=before)
                 .order_by("month")):
        due = da_percent_on(rule_set, slip.month)
        paid = _paid_percent(slip)
        if due <= paid:
            continue
        amount = calc.r(slip.basic_full * (due - paid) / 100 * slip.paid_days / slip.days_in_month)
        if amount > 0:
            out.append({"source": slip, "from": paid, "to": due, "amount": amount})
    return out


# ------------------------------------------------------------------ one staff member
def _lop(staff, month: date) -> Decimal:
    from apps.hr.services import lop_days

    start, end = first_of(month), last_of(month)
    lop = lop_days(staff=staff, start=start, end=end)
    # not in service for part of the month: joined late or relieved early
    if staff.date_joined > start:
        lop += Decimal(min((staff.date_joined - start).days, (end - start).days + 1))
    relieved = getattr(getattr(staff, "hr_profile", None), "relieved_on", None)
    if relieved and relieved < end:
        lop += Decimal((end - max(relieved, start)).days)
    return lop


def _components(structure: SalaryStructure, basic: Decimal) -> list[calc.Component]:
    overrides = {o.component_id: o.amount for o in structure.overrides.all()}
    out = []
    for c in PayComponent.objects.filter(rule_set=structure.rule_set):
        if c.pk in overrides:
            amount = overrides[c.pk]
        elif not c.applies_to_all:
            continue
        elif c.calc == PayComponent.Calc.PERCENT_BASIC:
            amount = basic * c.value / 100
        else:
            amount = c.value
        out.append(calc.Component(c.code, c.name, c.kind, Decimal(amount), c.taxable, c.prorate))
    return out


def _compute_one(*, run: PayrollRun, structure: SalaryStructure, st: calc.Statutory) -> Payslip:
    staff, month, rs = structure.staff, run.month, structure.rule_set
    basic = basic_of(structure)
    da_pct = da_percent_on(rs, month) if structure.da_applicable else ZERO
    hra_pct = Decimal(rs.hra_percent(structure.city_class)) if structure.hra_applicable else ZERO
    extras = [calc.Extra(f"once-{p.pk}", p.get_kind_display() + (f" — {p.note}" if p.note else ""), p.amount, p.taxable)
              for p in OneTimePayment.objects.filter(staff=staff, month=month)]
    arrears = due_arrears(staff=staff, rule_set=rs, before=month) if structure.da_applicable else []
    if arrears:
        span = f"{arrears[0]['source'].month:%b %Y}" + (f"–{arrears[-1]['source'].month:%b %Y}" if len(arrears) > 1 else "")
        extras.append(calc.Extra("da_arrears", f"DA arrears ({span})", sum((a["amount"] for a in arrears), ZERO), True, da=True))
    loans = []
    for loan in Loan.objects.filter(staff=staff, status=Loan.Status.ACTIVE, start_month__lte=month, balance__gt=0):
        loans.append((loan.pk, min(loan.monthly_recovery, loan.balance),
                      f"{loan.get_kind_display()} recovery (balance ₹{loan.balance - min(loan.monthly_recovery, loan.balance):,.0f})"))
    ytd = Payslip.objects.filter(staff=staff, run__status=RUN.LOCKED, month__gte=fy_start(month), month__lt=month).aggregate(
        t=Sum("taxable_gross"), d=Sum("tds"))
    days = calendar.monthrange(month.year, month.month)[1]
    inp = calc.Input(
        basic_full=basic, days_in_month=days, lop_days=_lop(staff, month), da_percent=da_pct, hra_percent=hra_pct,
        nps_employer_percent=rs.nps_employer_percent, pf=structure.pf, nps=structure.nps, esi=structure.esi,
        pt=structure.pt, tds=structure.tds, fixed_monthly_tds=structure.fixed_monthly_tds,
        components=_components(structure, basic), extras=extras, loans=loans,
        ytd_taxable=ytd["t"] or ZERO, ytd_tds=ytd["d"] or ZERO, months_left=months_left_in_fy(month),
    )
    res = calc.compute(inp, st)
    profile = getattr(staff, "hr_profile", None)
    slip = Payslip.objects.create(
        branch=run.branch, run=run, staff=staff, month=month, rule_set=rs, rule_set_code=rs.code,
        level=structure.level.code if structure.level else "", cell_index=structure.cell_index, basic_full=basic,
        da_percent=da_pct, days_in_month=days, lop_days=inp.lop_days, paid_days=res.paid_days,
        basic_earned=res.basic_earned, da_earned=res.da_earned, gross=res.gross, total_deductions=res.total_deductions,
        net_pay=res.net_pay, pf_wages=res.pf_wages, eps_wages=res.eps_wages, employer_epf=res.employer_epf,
        employer_eps=res.employer_eps, employer_nps=res.employer_nps, employer_esi=res.employer_esi, tds=res.tds,
        taxable_gross=res.taxable_gross, bank_account=getattr(profile, "bank_account", "") or "",
        ifsc=getattr(profile, "ifsc", "") or "",
    )
    PayslipLine.objects.bulk_create([PayslipLine(payslip=slip, code=ln.code, name=ln.name, kind=ln.kind, amount=ln.amount,
                                                 taxable=ln.taxable, sequence=i) for i, ln in enumerate(res.lines)])
    for a in arrears:
        ArrearPayment.objects.create(branch=run.branch, source=a["source"], paid_in=slip, from_percent=a["from"],
                                     to_percent=a["to"], amount=a["amount"])
    balances = {loan.pk: loan.balance for loan in Loan.objects.filter(pk__in=[lid for lid, _ in res.loan_recoveries])}
    LoanRecovery.objects.bulk_create([LoanRecovery(payslip=slip, loan_id=lid, amount=amt, balance_after=balances[lid] - amt)
                                      for lid, amt in res.loan_recoveries])
    return slip


def _payable_structures(branch, month: date):
    start = first_of(month)
    return (SalaryStructure.objects.select_related("staff__hr_profile", "rule_set", "level")
            .prefetch_related("overrides")
            .filter(branch=branch, is_active=True, staff__date_joined__lte=last_of(month))
            .filter(Q(staff__status=Staff.Status.ACTIVE) | Q(staff__hr_profile__relieved_on__gte=start)))


def _compute_all(run: PayrollRun) -> list[str]:
    st = statutory_input(statutory_for(run.branch))
    notes = []
    paid = set()
    for structure in _payable_structures(run.branch, run.month):
        try:
            with transaction.atomic():
                _compute_one(run=run, structure=structure, st=st)
            paid.add(structure.staff_id)
        except (calc.NegativeNet, Conflict) as exc:
            notes.append(f"{structure.staff.full_name}: not paid — {exc}")
    for s in Staff.objects.filter(branch=run.branch, status=Staff.Status.ACTIVE).exclude(pk__in=paid):
        if not SalaryStructure.objects.filter(staff=s, is_active=True).exists():
            notes.append(f"{s.full_name}: no salary structure")
    return notes


# ------------------------------------------------------------------ lifecycle
def _run(run) -> PayrollRun:
    return PayrollRun.objects.select_for_update().select_related("branch").get(pk=run.pk)


@transaction.atomic
def create_run(*, branch, month: date, by: str) -> PayrollRun:
    month = first_of(month)
    if month > first_of(timezone.localdate()):
        raise Conflict("Payroll can't be run for a future month.")
    if PayrollRun.objects.filter(branch=branch, month=month).exclude(status=RUN.REVERSED).exists():
        raise Conflict(f"A payroll run for {month:%B %Y} already exists.")
    later = PayrollRun.objects.filter(branch=branch, month__gt=month, status=RUN.LOCKED).first()
    if later:
        raise Conflict(f"{later.month:%B %Y} is already locked; reverse it before running an earlier month.")
    run = PayrollRun.objects.create(branch=branch, month=month, created_by=by)
    notes = apply_increments(branch=branch, month=month, by=by)
    notes += _compute_all(run)
    run.notes = notes
    run.save(update_fields=["notes", "updated_at"])
    record("payroll.run.created", actor=by, run=run.pk, month=str(month), payslips=run.payslips.count())
    return run


@transaction.atomic
def recompute(*, run: PayrollRun, by: str) -> PayrollRun:
    run = _run(run)
    if run.status != RUN.DRAFT:
        raise Conflict(f"Only a draft run can be recalculated; this one is {run.get_status_display().lower()}.")
    run.payslips.all().delete()
    notes = [n for n in run.notes if "increment" in n]
    run.notes = notes + _compute_all(run)
    run.save(update_fields=["notes", "updated_at"])
    record("payroll.run.recomputed", actor=by, run=run.pk)
    return run


@transaction.atomic
def submit(*, run: PayrollRun, by: str) -> PayrollRun:
    run = _run(run)
    if run.status != RUN.DRAFT:
        raise Conflict("Only a draft run can be sent for review.")
    if not run.payslips.exists():
        raise Conflict("This run has no payslips.")
    run.status = RUN.REVIEW
    run.save(update_fields=["status", "updated_at"])
    record("payroll.run.submitted", actor=by, run=run.pk)
    return run


@transaction.atomic
def back_to_draft(*, run: PayrollRun, by: str) -> PayrollRun:
    run = _run(run)
    if run.status != RUN.REVIEW:
        raise Conflict("Only a run in review can go back to draft.")
    run.status = RUN.DRAFT
    run.save(update_fields=["status", "updated_at"])
    record("payroll.run.back_to_draft", actor=by, run=run.pk)
    return run


@transaction.atomic
def lock(*, run: PayrollRun, by: str) -> PayrollRun:
    run = _run(run)
    if run.status != RUN.REVIEW:
        raise Conflict("A run is locked after review; send it for review first.")
    for rec in LoanRecovery.objects.filter(payslip__run=run).select_related("loan"):
        loan = Loan.objects.select_for_update().get(pk=rec.loan_id)
        if rec.amount > loan.balance:
            raise Conflict(f"{loan.staff.full_name}'s {loan.get_kind_display().lower()} balance changed; recalculate the run.")
        loan.balance -= rec.amount
        loan.status = Loan.Status.CLOSED if loan.balance == 0 else Loan.Status.ACTIVE
        loan.save(update_fields=["balance", "status", "updated_at"])
    run.status, run.locked_by, run.locked_at = RUN.LOCKED, by, timezone.now()
    run.save(update_fields=["status", "locked_by", "locked_at", "updated_at"])
    record("payroll.run.locked", actor=by, run=run.pk, month=str(run.month),
           net=str(run.payslips.aggregate(t=Sum("net_pay"))["t"] or 0))
    return run


@transaction.atomic
def reverse(*, run: PayrollRun, reason: str, by: str) -> PayrollRun:
    run = _run(run)
    if run.status != RUN.LOCKED:
        raise Conflict("Only a locked run is reversed; a draft or review run is simply recalculated.")
    if not (reason or "").strip():
        raise Conflict("Give the reason for reversing this month.")
    later = PayrollRun.objects.filter(branch=run.branch, month__gt=run.month).exclude(status=RUN.REVERSED).first()
    if later:
        raise Conflict(f"{later.month:%B %Y} has a run; reverse the latest month first.")
    for rec in LoanRecovery.objects.filter(payslip__run=run):
        loan = Loan.objects.select_for_update().get(pk=rec.loan_id)
        loan.balance += rec.amount
        loan.status = Loan.Status.ACTIVE
        loan.save(update_fields=["balance", "status", "updated_at"])
    run.status, run.reversed_by, run.reversed_at, run.reversal_reason = RUN.REVERSED, by, timezone.now(), reason.strip()
    run.save(update_fields=["status", "reversed_by", "reversed_at", "reversal_reason", "updated_at"])
    record("payroll.run.reversed", actor=by, run=run.pk, month=str(run.month), reason=reason.strip())
    return run


# ------------------------------------------------------------------ DA revision
@transaction.atomic
def revise_da(*, rule_set, percent: Decimal, effective_from: date, by: str, declared_on: date | None = None,
              note: str = "") -> DARate:
    effective_from = first_of(effective_from)
    rate, created = DARate.objects.update_or_create(
        rule_set=rule_set, effective_from=effective_from,
        defaults={"branch": rule_set.branch, "percent": percent, "declared_on": declared_on or timezone.localdate(),
                  "note": note})
    record("payroll.da.revised", actor=by, rule_set=rule_set.code, percent=str(percent),
           effective_from=str(effective_from), new=created)
    return rate


# ------------------------------------------------------------------ loans
@transaction.atomic
def create_loan(*, staff, kind: str, amount: Decimal, monthly_recovery: Decimal, start_month: date, note: str, by: str) -> Loan:
    if amount <= 0 or monthly_recovery <= 0:
        raise Conflict("Amount and monthly recovery must be more than zero.")
    if monthly_recovery > amount:
        raise Conflict("The monthly recovery is more than the amount.")
    start_month = first_of(start_month)
    guard_month_open(branch=staff.branch, month=start_month)
    loan = Loan.objects.create(branch=staff.branch, staff=staff, kind=kind, amount=amount, monthly_recovery=monthly_recovery,
                               start_month=start_month, balance=amount, note=note)
    record("payroll.loan.created", actor=by, loan=loan.pk, staff=staff.pk, amount=str(amount))
    return loan


# ------------------------------------------------------------------ outputs
def summary(run: PayrollRun) -> dict:
    agg = run.payslips.aggregate(gross=Sum("gross"), deductions=Sum("total_deductions"), net=Sum("net_pay"),
                                 epf=Sum("employer_epf"), eps=Sum("employer_eps"), nps=Sum("employer_nps"),
                                 esi=Sum("employer_esi"))
    return {"payslips": run.payslips.count(), **{k: v or ZERO for k, v in agg.items()}}


def line_totals(payslips) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for code, amount in PayslipLine.objects.filter(payslip__in=payslips).values_list("code", "amount"):
        out[code] += amount
    return dict(out)
