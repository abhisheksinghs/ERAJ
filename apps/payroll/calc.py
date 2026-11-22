"""
Salary arithmetic for one staff member and one month (ADR-009). Pure: no
database access, so every rule can be unit-tested with plain numbers.

Rounding: each line to whole rupees, half up; ESI rounded up (as ESIC does).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def r(x) -> Decimal:
    return Decimal(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def ceil(x) -> Decimal:
    return Decimal(x).quantize(Decimal("1"), rounding=ROUND_CEILING)


class NegativeNet(Exception):
    pass


@dataclass
class Component:
    code: str
    name: str
    kind: str  # earning | deduction
    amount: Decimal  # full-month amount
    taxable: bool = True
    prorate: bool = True


@dataclass
class Extra:
    code: str
    name: str
    amount: Decimal
    taxable: bool = True
    da: bool = False  # DA arrears: also PF / NPS wages


@dataclass
class Statutory:
    pf_employee_percent: Decimal = Decimal("12")
    pf_employer_percent: Decimal = Decimal("12")
    eps_percent: Decimal = Decimal("8.33")
    pf_wage_ceiling: Decimal = Decimal("15000")
    pf_cap_wages: bool = True
    nps_employee_percent: Decimal = Decimal("10")
    esi_employee_percent: Decimal = Decimal("0.75")
    esi_employer_percent: Decimal = Decimal("3.25")
    esi_wage_ceiling: Decimal = Decimal("21000")
    pt_slabs: list = field(default_factory=list)
    tds_slabs: list = field(default_factory=list)
    tds_standard_deduction: Decimal = Decimal("75000")
    tds_rebate_limit: Decimal = Decimal("1200000")
    tds_cess_percent: Decimal = Decimal("4")


@dataclass
class Input:
    basic_full: Decimal
    days_in_month: int
    lop_days: Decimal = ZERO
    da_percent: Decimal = ZERO
    hra_percent: Decimal = ZERO
    nps_employer_percent: Decimal = Decimal("14")
    pf: bool = False
    nps: bool = False
    esi: bool = False
    pt: bool = False
    tds: bool = False
    fixed_monthly_tds: Decimal | None = None
    components: list[Component] = field(default_factory=list)
    extras: list[Extra] = field(default_factory=list)
    loans: list[tuple[int, Decimal, str]] = field(default_factory=list)  # (loan id, recovery, label)
    ytd_taxable: Decimal = ZERO  # earlier months of this financial year
    ytd_tds: Decimal = ZERO
    months_left: int = 1  # including this month, to March


@dataclass
class Line:
    code: str
    name: str
    kind: str
    amount: Decimal
    taxable: bool = True


@dataclass
class Result:
    lines: list[Line]
    paid_days: Decimal
    basic_earned: Decimal
    da_earned: Decimal
    gross: Decimal
    taxable_gross: Decimal
    total_deductions: Decimal
    net_pay: Decimal
    pf_wages: Decimal = ZERO
    eps_wages: Decimal = ZERO
    employer_epf: Decimal = ZERO
    employer_eps: Decimal = ZERO
    employer_nps: Decimal = ZERO
    employer_esi: Decimal = ZERO
    tds: Decimal = ZERO
    loan_recoveries: list[tuple[int, Decimal]] = field(default_factory=list)

    def amount(self, code: str) -> Decimal:
        return sum((ln.amount for ln in self.lines if ln.code == code), ZERO)


def slab_amount(slabs: list, value: Decimal) -> Decimal:
    """Monthly PT: the slab whose range holds `value` ({"from", "to" (None = no upper), "amount"})."""
    for s in slabs:
        lo = Decimal(str(s.get("from", 0)))
        hi = s.get("to")
        if value >= lo and (hi in (None, "") or value <= Decimal(str(hi))):
            return Decimal(str(s.get("amount", 0)))
    return ZERO


def annual_tax(income: Decimal, st: Statutory) -> Decimal:
    taxable = max(ZERO, income - st.tds_standard_deduction)
    if taxable <= st.tds_rebate_limit:
        return ZERO
    tax = ZERO
    for s in st.tds_slabs:
        lo = Decimal(str(s.get("from", 0)))
        hi = s.get("to")
        top = taxable if hi in (None, "") else min(taxable, Decimal(str(hi)))
        if top > lo:
            tax += (top - lo) * Decimal(str(s.get("percent", 0))) / HUNDRED
    return r(tax * (1 + st.tds_cess_percent / HUNDRED))


def compute(inp: Input, st: Statutory) -> Result:
    days = Decimal(inp.days_in_month)
    lop = min(max(inp.lop_days, ZERO), days)
    paid = days - lop
    f = paid / days
    lines: list[Line] = []

    def earn(code, name, amount, taxable=True):
        if amount:
            lines.append(Line(code, name, "earning", amount, taxable))

    def deduct(code, name, amount):
        if amount:
            lines.append(Line(code, name, "deduction", amount, False))

    basic = r(inp.basic_full * f)
    da = r(inp.basic_full * inp.da_percent / HUNDRED * f)
    earn("basic", "Basic pay", basic)
    earn("da", f"Dearness allowance ({inp.da_percent.normalize():f}%)", da)
    earn("hra", "House rent allowance", r(inp.basic_full * inp.hra_percent / HUNDRED * f))
    for c in inp.components:
        if c.kind == "earning":
            earn(c.code, c.name, r(c.amount * f) if c.prorate else r(c.amount), c.taxable)
    da_extra = ZERO
    for e in inp.extras:
        earn(e.code, e.name, r(e.amount), e.taxable)
        if e.da:
            da_extra += r(e.amount)

    gross = sum((ln.amount for ln in lines), ZERO)
    taxable_gross = sum((ln.amount for ln in lines if ln.taxable), ZERO)
    res = Result(lines=lines, paid_days=paid, basic_earned=basic, da_earned=da, gross=gross,
                 taxable_gross=taxable_gross, total_deductions=ZERO, net_pay=ZERO)

    wages = basic + da + da_extra
    if inp.pf:
        res.eps_wages = min(wages, st.pf_wage_ceiling)
        res.pf_wages = res.eps_wages if st.pf_cap_wages else wages
        deduct("pf", "Provident fund", r(res.pf_wages * st.pf_employee_percent / HUNDRED))
        er = r(res.pf_wages * st.pf_employer_percent / HUNDRED)
        res.employer_eps = min(er, r(res.eps_wages * st.eps_percent / HUNDRED))
        res.employer_epf = er - res.employer_eps
    if inp.nps:
        deduct("nps", "NPS (employee)", r(wages * st.nps_employee_percent / HUNDRED))
        res.employer_nps = r(wages * inp.nps_employer_percent / HUNDRED)
    if inp.esi and gross <= st.esi_wage_ceiling:
        deduct("esi", "ESI", ceil(gross * st.esi_employee_percent / HUNDRED))
        res.employer_esi = ceil(gross * st.esi_employer_percent / HUNDRED)
    if inp.pt:
        deduct("pt", "Professional tax", slab_amount(st.pt_slabs, gross))
    if inp.tds:
        if inp.fixed_monthly_tds is not None:
            res.tds = r(inp.fixed_monthly_tds)
        else:
            regular = taxable_gross - sum((r(e.amount) for e in inp.extras if e.taxable), ZERO)
            projected = inp.ytd_taxable + taxable_gross + regular * max(inp.months_left - 1, 0)
            res.tds = max(ZERO, r((annual_tax(projected, st) - inp.ytd_tds) / max(inp.months_left, 1)))
        deduct("tds", "Income tax (TDS)", res.tds)
    for c in inp.components:
        if c.kind == "deduction":
            deduct(c.code, c.name, r(c.amount))

    before_loans = sum((ln.amount for ln in lines if ln.kind == "deduction"), ZERO)
    room = gross - before_loans
    if room < 0:
        raise NegativeNet(f"Deductions ₹{before_loans} exceed gross ₹{gross}.")
    for loan_id, recovery, label in inp.loans:
        amt = min(r(recovery), room)
        if amt > 0:
            deduct(f"loan-{loan_id}", label, amt)
            res.loan_recoveries.append((loan_id, amt))
            room -= amt
    for code, name, amount in (("employer_epf", "Employer EPF", res.employer_epf),
                               ("employer_eps", "Employer EPS", res.employer_eps),
                               ("employer_nps", "Employer NPS", res.employer_nps),
                               ("employer_esi", "Employer ESI", res.employer_esi)):
        if amount:
            lines.append(Line(code, name, "employer", amount, False))
    res.total_deductions = sum((ln.amount for ln in lines if ln.kind == "deduction"), ZERO)
    res.net_pay = gross - res.total_deductions
    return res
