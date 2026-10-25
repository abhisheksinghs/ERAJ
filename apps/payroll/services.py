from decimal import Decimal

from django.db import transaction

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.payroll.models import Payslip


@transaction.atomic
def generate_payslip(*, staff, period, basic_salary, allowances=Decimal("0"), deductions=Decimal("0")) -> Payslip:
    if Payslip.objects.filter(staff=staff, period=period).exists():
        raise Conflict("Payslip already generated for this staff member and month.")
    net_pay = basic_salary + allowances - deductions
    slip = Payslip.objects.create(
        branch=staff.branch,
        staff=staff,
        period=period,
        basic_salary=basic_salary,
        allowances=allowances,
        deductions=deductions,
        net_pay=net_pay,
    )
    record(
        "payroll.generated",
        detail={"payslip": slip.pk, "staff": staff.pk, "period": str(period), "net_pay": str(net_pay)},
    )
    return slip
