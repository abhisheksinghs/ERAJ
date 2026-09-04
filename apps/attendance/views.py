from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import RolePermission
from apps.attendance import services
from apps.attendance.models import AttendanceRecord, Student
from apps.attendance.serializers import (
    AttendanceRecordSerializer,
    AttendanceSummarySerializer,
    MarkAttendanceSerializer,
    StudentSerializer,
)


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    permission_classes = [RolePermission]
    search_fields = ["full_name", "roll_no"]
    filterset_fields = ["class_section"]
    ordering_fields = ["full_name", "created_at"]

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        return Response(AttendanceSummarySerializer(services.summary(student=self.get_object())).data)


class AttendanceRecordViewSet(
    mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = AttendanceRecord.objects.select_related("student").all()
    serializer_class = AttendanceRecordSerializer
    permission_classes = [RolePermission]
    filterset_fields = ["student", "date", "status"]
    ordering_fields = ["date", "created_at"]

    @action(detail=False, methods=["post"])
    def mark(self, request):
        data = MarkAttendanceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        rec = services.mark(
            marked_by=getattr(request.user, "email", ""), **data.validated_data
        )
        return Response(AttendanceRecordSerializer(rec).data, status=201)
