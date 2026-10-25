"""python manage.py test apps.payroll.tests.test_payslip"""
import datetime
from decimal import Decimal

from apps.core.exceptions import Conflict
from apps.core.testing import EraTestCase
from apps.payroll import services


class PayslipTest(EraTestCase):
    def setUp(self):
        super().setUp()
        self.employee = self.make_staff()

    def test_net_pay_computed(self):
        slip = services.generate_payslip(
            staff=self.employee,
            period=datetime.date(2026, 1, 1),
            basic_salary=Decimal("50000"),
            allowances=Decimal("5000"),
            deductions=Decimal("2000"),
        )
        self.assertEqual(slip.net_pay, Decimal("53000"))

    def test_blocks_duplicate_period(self):
        services.generate_payslip(
            staff=self.employee, period=datetime.date(2026, 1, 1), basic_salary=Decimal("50000")
        )
        with self.assertRaises(Conflict):
            services.generate_payslip(
                staff=self.employee, period=datetime.date(2026, 1, 1), basic_salary=Decimal("50000")
            )
