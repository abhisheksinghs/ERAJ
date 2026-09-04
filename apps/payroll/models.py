"""
Payroll module. TENANT_APPS. Depends on apps.hr's Employee.

NOT statutory-compliant payroll — flat basic + allowances - deductions, no
PF/ESI/TDS/tax-slab logic. Real payroll needs a compliance review per
jurisdiction before this touches real salaries.
"""
from django.db import models

from apps.core.mixins import TimeStamped
from apps.hr.models import Employee


class Payslip(TimeStamped):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="payslips")
    period = models.DateField(help_text="First of the month this payslip covers")
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2)
    allowances = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ("-period",)
        constraints = [
            models.UniqueConstraint(fields=["employee", "period"], name="payroll_one_payslip_per_employee_per_period"),
        ]

    def __str__(self) -> str:
        return f"{self.employee} — {self.period:%Y-%m}"
