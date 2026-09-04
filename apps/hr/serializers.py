from rest_framework import serializers

from apps.hr.models import Department, Employee


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ("id", "name")


class EmployeeSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)

    class Meta:
        model = Employee
        fields = (
            "id", "full_name", "email", "phone", "designation",
            "department", "department_name", "date_joined", "is_active", "created_at",
        )
        read_only_fields = ("created_at",)
