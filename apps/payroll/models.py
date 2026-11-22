"""
Payroll (ADR-009). Branch-owned (ADR-001), paying `people.Staff` (ADR-002).

Two government rule sets side by side (central, Bihar state): each has its own
pay matrix, DA history, HRA by city class and allowance components. Every rate,
ceiling and slab is data the accountant maintains; the code ships samples only.
Payslips are snapshots: once a run is locked nothing recomputes them.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.mixins import TimeStamped
from apps.org.models import BranchOwned


def money(**kw):
    return models.DecimalField(max_digits=12, decimal_places=2, **kw)


def pct(**kw):
    return models.DecimalField(max_digits=6, decimal_places=3, **kw)


class PayRuleSet(TimeStamped, BranchOwned):
    code = models.SlugField(max_length=30, help_text='e.g. "central-7cpc", "bihar-7cpc"')
    name = models.CharField(max_length=100)
    hra_x = pct(default=0, help_text="HRA % of basic for X-class cities")
    hra_y = pct(default=0)
    hra_z = pct(default=0)
    nps_employer_percent = pct(default=14, help_text="Government contribution % of basic + DA")

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=["branch", "code"], name="payroll_ruleset_code_unique")]

    def __str__(self) -> str:
        return self.name

    def hra_percent(self, city_class: str):
        return {"X": self.hra_x, "Y": self.hra_y, "Z": self.hra_z}.get(city_class, 0)


class PayLevel(TimeStamped, BranchOwned):
    rule_set = models.ForeignKey(PayRuleSet, on_delete=models.CASCADE, related_name="levels")
    code = models.CharField(max_length=10, help_text='Pay matrix level, e.g. "6"')
    sequence = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("rule_set", "sequence", "code")
        constraints = [models.UniqueConstraint(fields=["rule_set", "code"], name="payroll_level_unique")]

    def __str__(self) -> str:
        return f"{self.rule_set.code} L{self.code}"


class PayCell(TimeStamped, BranchOwned):
    level = models.ForeignKey(PayLevel, on_delete=models.CASCADE, related_name="cells")
    index = models.PositiveSmallIntegerField(help_text="Cell 1, 2, 3 … of the level")
    basic = money()

    class Meta:
        ordering = ("level", "index")
        constraints = [models.UniqueConstraint(fields=["level", "index"], name="payroll_cell_unique")]


class DARate(TimeStamped, BranchOwned):
    rule_set = models.ForeignKey(PayRuleSet, on_delete=models.CASCADE, related_name="da_rates")
    effective_from = models.DateField(help_text="First of a month")
    percent = pct()
    declared_on = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("rule_set", "-effective_from")
        constraints = [models.UniqueConstraint(fields=["rule_set", "effective_from"], name="payroll_da_unique")]

    def clean(self):
        if self.effective_from and self.effective_from.day != 1:
            raise ValidationError({"effective_from": "DA is revised from the 1st of a month."})


class PayComponent(TimeStamped, BranchOwned):
    """An allowance or deduction of a rule set (besides basic, DA, HRA and statutory ones)."""

    class Kind(models.TextChoices):
        EARNING = "earning", "Earning"
        DEDUCTION = "deduction", "Deduction"

    class Calc(models.TextChoices):
        FIXED = "fixed", "Fixed amount"
        PERCENT_BASIC = "percent_basic", "% of basic"

    rule_set = models.ForeignKey(PayRuleSet, on_delete=models.CASCADE, related_name="components")
    code = models.SlugField(max_length=20)
    name = models.CharField(max_length=80)
    name_hi = models.CharField(max_length=80, blank=True)
    kind = models.CharField(max_length=9, choices=Kind.choices, default=Kind.EARNING)
    calc = models.CharField(max_length=13, choices=Calc.choices, default=Calc.FIXED)
    value = models.DecimalField(max_digits=12, decimal_places=3, default=0, help_text="Amount, or % of basic")
    taxable = models.BooleanField(default=True)
    prorate = models.BooleanField(default=True, help_text="Reduced for loss-of-pay days")
    applies_to_all = models.BooleanField(default=True, help_text="Off = only staff given an amount on their structure")
    sequence = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("rule_set", "kind", "sequence", "code")
        constraints = [models.UniqueConstraint(fields=["rule_set", "code"], name="payroll_component_unique")]

    def __str__(self) -> str:
        return self.name


class StatutorySettings(TimeStamped, BranchOwned):
    """Rates, ceilings and slabs the accountant enters (sample values are not advice).

    pt_slabs:  [{"from": 0, "to": 25000, "amount": 0}, …]  monthly gross → monthly PT
    tds_slabs: [{"from": 0, "to": 400000, "percent": 0}, …] annual taxable income
    """

    pf_employee_percent = pct(default=12)
    pf_employer_percent = pct(default=12)
    eps_percent = pct(default="8.33")
    pf_wage_ceiling = money(default=15000)
    pf_cap_wages = models.BooleanField(default=True, help_text="Employee PF on wages up to the ceiling only")
    nps_employee_percent = pct(default=10)
    esi_employee_percent = pct(default="0.75")
    esi_employer_percent = pct(default="3.25")
    esi_wage_ceiling = money(default=21000)
    pt_slabs = models.JSONField(default=list, blank=True)
    tds_slabs = models.JSONField(default=list, blank=True)
    tds_standard_deduction = money(default=75000)
    tds_rebate_limit = money(default=1200000, help_text="No tax when taxable income is up to this (sec. 87A)")
    tds_cess_percent = pct(default=4)

    class Meta:
        verbose_name_plural = "statutory settings"
        constraints = [models.UniqueConstraint(fields=["branch"], name="payroll_one_statutory_per_branch")]


class SalaryStructure(TimeStamped, BranchOwned):
    class City(models.TextChoices):
        X = "X", "X"
        Y = "Y", "Y"
        Z = "Z", "Z"

    staff = models.OneToOneField("people.Staff", on_delete=models.CASCADE, related_name="salary_structure")
    rule_set = models.ForeignKey(PayRuleSet, on_delete=models.PROTECT, related_name="structures")
    level = models.ForeignKey(PayLevel, null=True, blank=True, on_delete=models.PROTECT, related_name="structures")
    cell_index = models.PositiveSmallIntegerField(null=True, blank=True)
    fixed_basic = money(null=True, blank=True, help_text="For staff outside the pay matrix (contract, part-time)")
    city_class = models.CharField(max_length=1, choices=City.choices, default=City.Z)
    increment_month = models.PositiveSmallIntegerField(default=7, help_text="1 = January, 7 = July; 0 = no increment")
    last_increment_on = models.DateField(null=True, blank=True)
    da_applicable = models.BooleanField(default=True)
    hra_applicable = models.BooleanField(default=True)
    pf = models.BooleanField(default=False)
    nps = models.BooleanField(default=False)
    esi = models.BooleanField(default=False)
    pt = models.BooleanField(default=True)
    tds = models.BooleanField(default=True)
    fixed_monthly_tds = money(null=True, blank=True, help_text="Use instead of the slab projection (old regime)")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("staff__full_name",)
        constraints = [
            models.CheckConstraint(check=~(Q(pf=True) & Q(nps=True)), name="payroll_pf_xor_nps"),
            models.CheckConstraint(
                check=Q(fixed_basic__isnull=False) | (Q(level__isnull=False) & Q(cell_index__isnull=False)),
                name="payroll_structure_has_basic"),
        ]

    def __str__(self) -> str:
        return f"{self.staff} — {self.rule_set.code}"


class StructureComponent(TimeStamped, BranchOwned):
    """A staff member's own amount for a component (overrides the rule set's value)."""

    structure = models.ForeignKey(SalaryStructure, on_delete=models.CASCADE, related_name="overrides")
    component = models.ForeignKey(PayComponent, on_delete=models.CASCADE, related_name="overrides")
    amount = money()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["structure", "component"], name="payroll_override_unique")]


class Loan(TimeStamped, BranchOwned):
    class Kind(models.TextChoices):
        LOAN = "loan", "Loan"
        ADVANCE = "advance", "Advance"

    class Status(models.TextChoices):
        ACTIVE = "active", "Recovering"
        CLOSED = "closed", "Repaid"

    staff = models.ForeignKey("people.Staff", on_delete=models.PROTECT, related_name="loans")
    kind = models.CharField(max_length=7, choices=Kind.choices, default=Kind.ADVANCE)
    amount = money()
    monthly_recovery = money()
    start_month = models.DateField(help_text="First month of recovery (1st of month)")
    balance = money()
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.ACTIVE)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-start_month",)
        constraints = [
            models.CheckConstraint(check=Q(balance__gte=0), name="payroll_loan_balance_nonneg"),
            models.CheckConstraint(check=Q(monthly_recovery__gt=0), name="payroll_loan_recovery_positive"),
        ]


class OneTimePayment(TimeStamped, BranchOwned):
    class Kind(models.TextChoices):
        BONUS = "bonus", "Bonus"
        INCREMENT_ARREARS = "increment_arrears", "Increment arrears"
        ARREARS = "arrears", "Other arrears"
        OTHER = "other", "Other payment"

    staff = models.ForeignKey("people.Staff", on_delete=models.PROTECT, related_name="one_time_payments")
    month = models.DateField(help_text="Paid with this month's salary (1st of month)")
    kind = models.CharField(max_length=17, choices=Kind.choices, default=Kind.BONUS)
    amount = money()
    taxable = models.BooleanField(default=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-month", "staff__full_name")


class PayrollRun(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "In review"
        LOCKED = "locked", "Locked"
        REVERSED = "reversed", "Reversed"

    month = models.DateField(help_text="1st of the month")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    created_by = models.CharField(max_length=255, blank=True)
    locked_by = models.CharField(max_length=255, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.CharField(max_length=255, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.CharField(max_length=500, blank=True)
    notes = models.JSONField(default=list, blank=True, help_text="Increments applied, staff skipped …")

    class Meta:
        ordering = ("-month",)
        constraints = [
            models.UniqueConstraint(fields=["branch", "month"], condition=~Q(status="reversed"),
                                    name="payroll_one_live_run_per_month"),
        ]

    def __str__(self) -> str:
        return f"Payroll {self.month:%B %Y} ({self.status})"


class Payslip(TimeStamped, BranchOwned):
    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="payslips")
    staff = models.ForeignKey("people.Staff", on_delete=models.PROTECT, related_name="payslips")
    month = models.DateField()
    # snapshot of what the calculation used
    rule_set_code = models.CharField(max_length=30)
    rule_set = models.ForeignKey(PayRuleSet, null=True, on_delete=models.SET_NULL, related_name="payslips")
    level = models.CharField(max_length=10, blank=True)
    cell_index = models.PositiveSmallIntegerField(null=True, blank=True)
    basic_full = money(help_text="Monthly basic before loss of pay")
    da_percent = pct(default=0)
    days_in_month = models.PositiveSmallIntegerField()
    lop_days = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    paid_days = models.DecimalField(max_digits=4, decimal_places=1)
    basic_earned = money()
    da_earned = money(default=0)
    gross = money()
    total_deductions = money()
    net_pay = money()
    pf_wages = money(default=0)
    eps_wages = money(default=0)
    employer_epf = money(default=0)
    employer_eps = money(default=0)
    employer_nps = money(default=0)
    employer_esi = money(default=0)
    tds = money(default=0)
    taxable_gross = money(default=0)
    # payment snapshot
    bank_account = models.CharField(max_length=20, blank=True)
    ifsc = models.CharField(max_length=11, blank=True)

    class Meta:
        ordering = ("run", "staff__full_name")
        constraints = [models.UniqueConstraint(fields=["run", "staff"], name="payroll_one_payslip_per_run")]
        indexes = [models.Index(fields=["staff", "month"], name="payroll_slip_staff_month")]

    def __str__(self) -> str:
        return f"{self.staff} — {self.month:%Y-%m}"


class PayslipLine(models.Model):
    class Kind(models.TextChoices):
        EARNING = "earning", "Earning"
        DEDUCTION = "deduction", "Deduction"
        EMPLOYER = "employer", "Employer contribution"

    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name="lines")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=9, choices=Kind.choices)
    amount = money()
    taxable = models.BooleanField(default=True)
    sequence = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("payslip", "kind", "sequence")


class ArrearPayment(TimeStamped, BranchOwned):
    """DA arrears for an earlier (locked) payslip, paid in a later payslip."""

    source = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name="arrears_out")
    paid_in = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name="arrears_in")
    from_percent = pct()
    to_percent = pct()
    amount = money()

    class Meta:
        ordering = ("source__month",)
        constraints = [models.UniqueConstraint(fields=["source", "paid_in"], name="payroll_arrear_once_per_payslip")]


class LoanRecovery(models.Model):
    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name="recoveries")
    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name="recoveries")
    amount = money()
    balance_after = money()
