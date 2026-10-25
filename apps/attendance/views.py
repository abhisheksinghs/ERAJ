from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.attendance import services
from apps.attendance.models import AttendanceRecord
from apps.attendance.serializers import (
    AttendanceRecordSerializer,
    AttendanceSummarySerializer,
    MarkAttendanceSerializer,
)
from apps.org.mixins import BranchScopedViewSetMixin
from apps.people.models import Student


class AttendanceRecordViewSet(
    BranchScopedViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = AttendanceRecord.objects.select_related("student").all()
    serializer_class = AttendanceRecordSerializer
    perm_resource = "attendance.record"
    action_perms = {"mark": "attendance.record.mark"}
    filterset_fields = ["student", "date", "status", "period", "subject"]
    ordering_fields = ["date", "created_at"]

    @action(detail=False, methods=["post"])
    def mark(self, request):
        data = MarkAttendanceSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        rec = services.mark(marked_by=getattr(request.user, "email", ""), **data.validated_data)
        return Response(AttendanceRecordSerializer(rec).data, status=201)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        student_id = request.query_params.get("student")
        if not student_id:
            raise ValidationError({"student": "query parameter is required"})
        student = Student.objects.filter(pk=student_id, branch_id__in=self._scope_ids()).first()
        if student is None:
            raise ValidationError({"student": "not found"})
        data = services.summary(
            student=student,
            date_from=request.query_params.get("from"),
            date_to=request.query_params.get("to"),
        )
        return Response(AttendanceSummarySerializer(data).data)

    def _scope_ids(self):
        from apps.org.scope import resolve_scope

        return resolve_scope(self.request).branch_ids
