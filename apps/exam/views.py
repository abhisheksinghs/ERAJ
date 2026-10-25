from django.db.models import Count
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.exam import pdf, services
from apps.exam.models import Exam, ExamSubject, GradeScale
from apps.exam.serializers import ExamSerializer, ExamSubjectSerializer, GradeScaleSerializer, LockSerializer, SaveMarksSerializer
from apps.org.mixins import BranchScopedViewSetMixin
from apps.org.permissions import request_can
from apps.org.scope import resolve_scope
from apps.people.models import Section, Student, staff_for_user


def _who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


def _get(request, model, name: str, required: bool = True):
    raw = request.query_params.get(name)
    if not raw:
        if required:
            raise ValidationError({name: "This parameter is required."})
        return None
    obj = model.objects.filter(pk=raw, branch_id__in=resolve_scope(request).branch_ids).first()
    if obj is None:
        raise ValidationError({name: "Not found."})
    return obj


def _pdf(body: bytes, name: str) -> HttpResponse:
    resp = HttpResponse(body, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{name}.pdf"'
    return resp


class GradeScaleViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = GradeScale.objects.prefetch_related("bands")
    serializer_class = GradeScaleSerializer
    perm_resource = "exam.setup"


class ExamViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = ExamSerializer
    perm_resource = "exam.setup"
    action_perms = {"publish": "exam.result.publish", "unpublish": "exam.result.publish"}
    filterset_fields = ["academic_year", "program", "term", "scale"]
    search_fields = ["name", "program__name"]

    def get_queryset(self):
        self.queryset = Exam.objects.select_related("program", "scale", "term").annotate(subject_count=Count("subjects"))
        return super().get_queryset()

    @extend_schema(request=None, responses=ExamSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return Response(ExamSerializer(services.publish(exam=self.get_object(), by=_who(request))).data)

    @extend_schema(request=None, responses=ExamSerializer)
    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        return Response(ExamSerializer(services.publish(exam=self.get_object(), by=_who(request), publish=False)).data)

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="date-sheet")
    def date_sheet(self, request, pk=None):
        exam = self.get_object()
        return _pdf(pdf.date_sheet_pdf(exam), f"date-sheet-{exam.pk}")


class ExamSubjectViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ExamSubject.objects.select_related("exam__program", "subject")
    serializer_class = ExamSubjectSerializer
    perm_resource = "exam.setup"
    filterset_fields = ["exam", "subject"]


class MarksViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    """Marks grid per exam subject and section; lock / unlock per exam and section."""

    perm_resource = "exam.marks"
    action_perms = {"save": "exam.marks.enter", "lock": "exam.marks.lock", "unlock": "exam.marks.unlock"}
    queryset = ExamSubject.objects.none()

    def _check_subject(self, exam_subject, section):
        if request_can(self.request, "exam.marks.all_subjects"):
            return
        if not services.may_enter(staff=staff_for_user(self.request.user), exam_subject=exam_subject, section=section):
            raise PermissionDenied("You can enter marks only for the subjects you teach in this section.")

    @extend_schema(parameters=[OpenApiParameter("exam_subject", int), OpenApiParameter("section", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def grid(self, request):
        es, section = _get(request, ExamSubject, "exam_subject"), _get(request, Section, "section")
        self._check_subject(es, section)
        return Response(services.grid(exam_subject=es, section=section))

    @extend_schema(request=SaveMarksSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def save(self, request):
        data = SaveMarksSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        v = data.validated_data
        self._check_subject(v["exam_subject"], v["section"])
        n = services.save_marks(exam_subject=v["exam_subject"], section=v["section"], rows=v["rows"], by=_who(request))
        return Response({"saved": n})

    @extend_schema(request=LockSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def lock(self, request):
        data = LockSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if not request_can(request, "exam.marks.all_subjects"):
            staff = staff_for_user(request.user)
            if staff is None or v["section"].class_teacher_id != staff.pk:
                raise PermissionDenied("Only the class teacher (or Admin) locks a section's marks.")
        services.lock(exam=v["exam"], section=v["section"], by=_who(request))
        return Response({"locked": True})

    @extend_schema(request=LockSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def unlock(self, request):
        data = LockSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if not v["reason"]:
            raise ValidationError({"reason": "Say why the marks are being unlocked."})
        services.unlock(exam=v["exam"], section=v["section"], by=_who(request), reason=v["reason"])
        return Response({"locked": False})


class ResultViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    perm_resource = "exam.result"
    queryset = Exam.objects.none()

    def _exams(self, request) -> list[Exam]:
        ids = [x for x in (request.query_params.get("exams") or "").split(",") if x.strip().isdigit()]
        exams = list(Exam.objects.filter(pk__in=ids, branch_id__in=resolve_scope(request).branch_ids).order_by("sequence"))
        if not exams or len(exams) != len(ids):
            raise ValidationError({"exams": "Give exam ids, comma separated."})
        return exams

    @extend_schema(parameters=[OpenApiParameter("exam", int), OpenApiParameter("section", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path="exam")
    def exam_result(self, request):
        return Response(services.exam_results(_get(request, Exam, "exam"), _get(request, Section, "section", required=False)))

    @extend_schema(parameters=[OpenApiParameter("exam", int), OpenApiParameter("section", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def analysis(self, request):
        return Response(services.analysis(_get(request, Exam, "exam"), _get(request, Section, "section", required=False)))

    @extend_schema(parameters=[OpenApiParameter("exams", str), OpenApiParameter("section", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def annual(self, request):
        return Response(services.annual_results(exams=self._exams(request), section=_get(request, Section, "section", required=False)))

    @extend_schema(parameters=[OpenApiParameter("student", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def cgpa(self, request):
        return Response(services.cgpa(_get(request, Student, "student")))

    @extend_schema(parameters=[OpenApiParameter("exam", int), OpenApiParameter("section", int), OpenApiParameter("student", int)],
                   responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=False, methods=["get"], url_path="report-cards")
    def report_cards(self, request):
        """Report cards as one PDF: a whole section, or one student."""
        exam = _get(request, Exam, "exam")
        section, student = _get(request, Section, "section", required=False), _get(request, Student, "student", required=False)
        if section is None and student is None:
            raise ValidationError({"section": "Give a section or a student."})
        res = services.exam_results(exam, section)
        rows = [r for r in res["rows"] if student is None or r["student"] == student.pk]
        return _pdf(pdf.report_cards_pdf(exam=exam, result=res, rows=rows), f"report-cards-{exam.pk}")

    @extend_schema(parameters=[OpenApiParameter("exams", str), OpenApiParameter("section", int), OpenApiParameter("student", int)],
                   responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=False, methods=["get"], url_path="annual-cards")
    def annual_cards(self, request):
        exams = self._exams(request)
        section, student = _get(request, Section, "section", required=False), _get(request, Student, "student", required=False)
        res = services.annual_results(exams=exams, section=section)
        rows = [r for r in res["rows"] if student is None or r["student"] == student.pk]
        return _pdf(pdf.annual_cards_pdf(exams=exams, result=res, rows=rows), "annual-cards")
