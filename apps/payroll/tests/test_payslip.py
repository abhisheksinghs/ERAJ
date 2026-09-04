"""python manage.py test apps.payroll.tests.test_payslip"""
import datetime
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase

from apps.core.exceptions import Conflict
from apps.hr.models import Employee
from apps.payroll import services


class PayslipTest(TenantTestCase):
    def setUp(self):
        self.employee = Employee.objects.create(full_name="E1", email="e1@x.com")

    def test_net_pay_computed(self):
        slip = services.generate_payslip(
            employee=self.employee,
            period=datetime.date(2026, 1, 1),
            basic_salary=Decimal("50000"),
            allowances=Decimal("5000"),
            deductions=Decimal("2000"),
        )
        self.assertEqual(slip.net_pay, Decimal("53000"))

    def test_blocks_duplicate_period(self):
        services.generate_payslip(
            employee=self.employee, period=datetime.date(2026, 1, 1), basic_salary=Decimal("50000")
        )
        with self.assertRaises(Conflict):
            services.generate_payslip(
                employee=self.employee, period=datetime.date(2026, 1, 1), basic_salary=Decimal("50000")
            )
