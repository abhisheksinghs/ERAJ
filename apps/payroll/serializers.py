from rest_framework import serializers

from apps.hr.models import Employee
from apps.payroll.models import Payslip


class PayslipSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)

    class Meta:
        model = Payslip
        fields = (
            "id", "employee", "employee_name", "period",
            "basic_salary", "allowances", "deductions", "net_pay", "created_at",
        )
        read_only_fields = ("net_pay", "created_at")


class GeneratePayslipSerializer(serializers.Serializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
    period = serializers.DateField(help_text="Any date in the target month; day is ignored by convention")
    basic_salary = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    allowances = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False, default=0)
    deductions = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False, default=0)
