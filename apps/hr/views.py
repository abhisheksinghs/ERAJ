from rest_framework import viewsets

from apps.accounts.permissions import RolePermission
from apps.hr.models import Department, Employee
from apps.hr.serializers import DepartmentSerializer, EmployeeSerializer


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [RolePermission]
    search_fields = ["name"]


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related("department").all()
    serializer_class = EmployeeSerializer
    permission_classes = [RolePermission]
    filterset_fields = ["department", "is_active"]
    search_fields = ["full_name", "email", "designation"]
    ordering_fields = ["full_name", "date_joined", "created_at"]
