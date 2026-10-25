from decimal import Decimal

from rest_framework import serializers

from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.payroll.models import Payslip
from apps.people.models import Staff


class PayslipSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)

    class Meta:
        model = Payslip
        fields = (
            "id", "branch", "staff", "staff_name", "period",
            "basic_salary", "allowances", "deductions", "net_pay", "created_at",
        )
        read_only_fields = ("net_pay", "created_at")


class GeneratePayslipSerializer(serializers.Serializer):
    staff = ScopedPrimaryKeyRelatedField(queryset=Staff.objects.all())
    period = serializers.DateField(help_text="Any date in the target month; stored as the 1st")
    basic_salary = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    allowances = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, default=0)
    deductions = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, default=0)

    def validate_period(self, value):
        return value.replace(day=1)
