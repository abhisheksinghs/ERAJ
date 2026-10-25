"""
Payroll module. TENANT app; branch-owned (ADR-001), paying `people.Staff`
(ADR-002).

NOT statutory-compliant yet — flat basic + allowances - deductions. M4 replaces
this with pay rule sets (central + Bihar), pay matrix, DA arrears and
PF/NPS/ESI/PT/TDS.
"""
from django.db import models

from apps.core.mixins import TimeStamped
from apps.org.models import BranchOwned


class Payslip(TimeStamped, BranchOwned):
    staff = models.ForeignKey("people.Staff", on_delete=models.PROTECT, related_name="payslips")
    period = models.DateField(help_text="First of the month this payslip covers")
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ("-period",)
        constraints = [
            models.UniqueConstraint(fields=["staff", "period"], name="payroll_one_payslip_per_staff_per_period"),
        ]

    def __str__(self) -> str:
        return f"{self.staff} — {self.period:%Y-%m}"
