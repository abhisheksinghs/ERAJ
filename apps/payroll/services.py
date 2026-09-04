from decimal import Decimal

from django.db import transaction

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.payroll.models import Payslip


@transaction.atomic
def generate_payslip(*, employee, period, basic_salary, allowances=Decimal("0"), deductions=Decimal("0")) -> Payslip:
    if Payslip.objects.filter(employee=employee, period=period).exists():
        raise Conflict("Payslip already generated for this employee and period.")
    net_pay = basic_salary + allowances - deductions
    slip = Payslip.objects.create(
        employee=employee,
        period=period,
        basic_salary=basic_salary,
        allowances=allowances,
        deductions=deductions,
        net_pay=net_pay,
    )
    record(
        "payroll.generated",
        detail={"payslip": slip.pk, "employee": employee.pk, "period": str(period), "net_pay": str(net_pay)},
    )
    return slip
