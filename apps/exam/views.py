from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.exam import services
from apps.exam.models import ExamResult
from apps.exam.serializers import ExamResultSerializer, RecordResultSerializer, StudentReportSerializer
from apps.org.mixins import BranchScopedViewSetMixin
from apps.org.scope import resolve_scope
from apps.people.models import Student


class ExamResultViewSet(
    BranchScopedViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = ExamResult.objects.select_related("student", "subject").all()
    serializer_class = ExamResultSerializer
    perm_resource = "exam.result"
    action_perms = {"record": "exam.marks.enter"}
    filterset_fields = ["student", "subject", "exam_name"]
    ordering_fields = ["created_at"]

    @action(detail=False, methods=["post"])
    def record(self, request):
        data = RecordResultSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        result = services.record_result(**data.validated_data)
        return Response(ExamResultSerializer(result).data, status=201)

    @action(detail=False, methods=["get"])
    def report(self, request):
        student = Student.objects.filter(
            pk=request.query_params.get("student") or 0, branch_id__in=resolve_scope(request).branch_ids
        ).first()
        if student is None:
            raise ValidationError({"student": "query parameter is required and must be a student in scope"})
        return Response(StudentReportSerializer(services.student_report(student=student)).data)
