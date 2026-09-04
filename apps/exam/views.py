from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import RolePermission
from apps.exam import services
from apps.exam.models import ExamResult, Student, Subject
from apps.exam.serializers import (
    ExamResultSerializer,
    RecordResultSerializer,
    StudentReportSerializer,
    StudentSerializer,
    SubjectSerializer,
)


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    permission_classes = [RolePermission]
    search_fields = ["full_name", "roll_no"]
    filterset_fields = ["class_section"]

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        return Response(StudentReportSerializer(services.student_report(student=self.get_object())).data)


class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [RolePermission]
    search_fields = ["name"]


class ExamResultViewSet(
    mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = ExamResult.objects.select_related("student", "subject").all()
    serializer_class = ExamResultSerializer
    permission_classes = [RolePermission]
    filterset_fields = ["student", "subject", "exam_name"]
    ordering_fields = ["created_at"]

    @action(detail=False, methods=["post"])
    def record(self, request):
        data = RecordResultSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = services.record_result(**data.validated_data)
        return Response(ExamResultSerializer(result).data, status=201)
