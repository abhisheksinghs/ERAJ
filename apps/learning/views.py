from datetime import date

from django.db.models import Count, Exists, OuterRef
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.files import LEARNING, check_upload, content_type, download
from apps.learning import services
from apps.learning.models import DiaryEntry, Homework, HomeworkFile, Material, OnlineClass, OnlineTest, Submission, SubmissionFile
from apps.learning.serializers import (
    DiaryEntrySerializer, GradeSerializer, HomeworkSerializer, MaterialSerializer, OnlineClassSerializer,
    OnlineTestSerializer, SubmissionSerializer,
)
from apps.org.mixins import BranchScopedViewSetMixin
from apps.org.permissions import request_can
from apps.org.scope import resolve_scope
from apps.people.models import Section, TeachingAssignment, staff_for_user


def who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


class TeacherScoped:
    """Teachers see and change only their own sections × subjects; Admin (learning.all_sections) all."""

    section_field = "section"
    subject_field = "subject"

    def all_sections(self) -> bool:
        return request_can(self.request, "learning.all_sections")

    def me(self):
        return staff_for_user(self.request.user)

    def scope(self, qs):
        if self.all_sections():
            return qs
        mine = TeachingAssignment.objects.filter(staff=self.me(), section=OuterRef(self.section_field),
                                                 subject=OuterRef(self.subject_field))
        return qs.filter(Exists(mine))

    def check(self, section, subject):
        services.check_teacher(staff=self.me(), section=section, subject=subject, any_section=self.all_sections())

    def stamp(self, serializer, **extra):
        v = serializer.validated_data
        section = v.get("section") or getattr(serializer.instance, "section", None)
        subject = v.get("subject") or getattr(serializer.instance, "subject", None)
        if section is not None and subject is not None:
            self.check(section, subject)
        if serializer.instance is None:
            return serializer.save(branch=self.active_branch(), teacher=self.me(), **extra)
        return serializer.save(**extra)


class HomeworkViewSet(TeacherScoped, BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Homework.objects.none()
    serializer_class = HomeworkSerializer
    perm_resource = "learning.homework"
    action_perms = {"attach": "learning.homework.manage"}
    filterset_fields = ["section", "subject", "due_date"]
    search_fields = ["title"]

    def get_queryset(self):
        self.queryset = (Homework.objects.select_related("section__program", "subject", "teacher").prefetch_related("files")
                         .annotate(submitted=Count("submissions")).order_by("-due_date", "-pk"))
        return self.scope(super().get_queryset())

    def perform_create(self, serializer):
        hw = self.stamp(serializer, created_by=who(self.request))
        services.homework_set(hw)

    def perform_update(self, serializer):
        self.stamp(serializer)

    @extend_schema(request={"multipart/form-data": OpenApiTypes.OBJECT}, responses=HomeworkSerializer)
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def attach(self, request, pk=None):
        hw = self.get_object()
        files = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not files:
            raise ValidationError({"files": "Attach at least one file."})
        for f in files:
            check_upload(f, allowed=LEARNING, max_mb=10)
        for f in files:
            HomeworkFile.objects.create(homework=hw, file=f, original_name=f.name[:255], content_type=content_type(f.name), size=f.size)
        return Response(HomeworkSerializer(self.get_queryset().get(pk=hw.pk), context={"request": request}).data)

    @extend_schema(parameters=[OpenApiParameter("file", int)], responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        f = self.get_object().files.filter(pk=request.query_params.get("file")).first()
        if f is None:
            raise NotFound()
        return download(f.file, f.original_name, f.content_type)


class SubmissionViewSet(TeacherScoped, BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Submission.objects.none()
    serializer_class = SubmissionSerializer
    perm_resource = "learning.submission"
    action_perms = {"grade": "learning.submission.manage"}
    section_field = "homework__section"
    subject_field = "homework__subject"
    filterset_fields = ["homework", "student", "late"]

    def get_queryset(self):
        self.queryset = Submission.objects.select_related("student", "homework").prefetch_related("files")
        return self.scope(super().get_queryset())

    @extend_schema(request=GradeSerializer, responses=SubmissionSerializer)
    @action(detail=True, methods=["post"])
    def grade(self, request, pk=None):
        s = GradeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        sub = services.grade(submission=self.get_object(), grade=s.validated_data["grade"],
                             remarks=s.validated_data["remarks"], by=who(request))
        return Response(SubmissionSerializer(sub, context={"request": request}).data)

    @extend_schema(parameters=[OpenApiParameter("file", int)], responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        f = SubmissionFile.objects.filter(submission=self.get_object(), pk=request.query_params.get("file")).first()
        if f is None:
            raise NotFound()
        return download(f.file, f.original_name, f.content_type)


class MaterialViewSet(TeacherScoped, BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Material.objects.none()
    serializer_class = MaterialSerializer
    perm_resource = "learning.material"
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ["program", "section", "subject", "kind"]
    search_fields = ["title", "chapter"]

    def get_queryset(self):
        self.queryset = Material.objects.select_related("program", "section", "subject")
        qs = super().get_queryset()
        if self.all_sections():
            return qs
        me = self.me()
        return qs.filter(subject__teaching_assignments__staff=me).distinct()

    def _file(self, serializer):
        f = serializer.validated_data.pop("upload", None)
        return {"file": f, "original_name": f.name[:255], "content_type": content_type(f.name)} if f else {}

    def perform_create(self, serializer):
        extra = self._file(serializer)
        v = serializer.validated_data
        if not self.all_sections() and not TeachingAssignment.objects.filter(staff=self.me(), subject=v["subject"]).exists():
            from apps.core.exceptions import Conflict

            raise Conflict(f"You don't teach {v['subject']}.")
        serializer.save(branch=self.active_branch(), teacher=self.me(), **extra)

    def perform_update(self, serializer):
        serializer.save(**self._file(serializer))

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        m = self.get_object()
        if not m.file:
            raise NotFound()
        return download(m.file, m.original_name, m.content_type)


class OnlineClassViewSet(TeacherScoped, BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = OnlineClass.objects.none()
    serializer_class = OnlineClassSerializer
    perm_resource = "learning.class"
    filterset_fields = ["section", "subject"]

    def get_queryset(self):
        self.queryset = OnlineClass.objects.select_related("section__program", "subject").annotate(joined=Count("joins")).order_by("-starts_at")
        return self.scope(super().get_queryset())

    def perform_create(self, serializer):
        self.stamp(serializer)

    def perform_update(self, serializer):
        self.stamp(serializer)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def joins(self, request, pk=None):
        c = self.get_object()
        joined = {j.student_id: j for j in c.joins.all()}
        rows = [{"student": s.pk, "name": s.full_name, "admission_no": s.admission_no,
                 "opened_at": joined[s.pk].first_opened_at if s.pk in joined else None,
                 "opens": joined[s.pk].opens if s.pk in joined else 0} for s in services.section_students(c.section)]
        return Response({"class": c.pk, "title": c.title, "joined": len(joined), "of": len(rows), "rows": rows})


class OnlineTestViewSet(TeacherScoped, BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = OnlineTest.objects.none()
    serializer_class = OnlineTestSerializer
    perm_resource = "learning.test"
    filterset_fields = ["section", "subject", "published"]

    def get_queryset(self):
        self.queryset = OnlineTest.objects.select_related("section__program", "subject").prefetch_related("questions")
        return self.scope(super().get_queryset())

    def perform_create(self, serializer):
        self.stamp(serializer)

    def perform_update(self, serializer):
        self.stamp(serializer)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        return Response(services.test_results(self.get_object()))


class DiaryViewSet(TeacherScoped, BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = DiaryEntry.objects.none()
    serializer_class = DiaryEntrySerializer
    perm_resource = "learning.diary"
    filterset_fields = {"section": ["exact"], "subject": ["exact"], "date": ["exact", "gte", "lte"]}

    def get_queryset(self):
        self.queryset = DiaryEntry.objects.select_related("section__program", "subject", "teacher")
        return self.scope(super().get_queryset())

    def perform_create(self, serializer):
        self.stamp(serializer)

    def perform_update(self, serializer):
        self.stamp(serializer)


class LearningReportViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    perm_resource = "learning.report"
    queryset = Homework.objects.none()

    def _range(self, request):
        today = timezone.localdate()
        def d(name, default):
            raw = request.query_params.get(name)
            try:
                return date.fromisoformat(raw) if raw else default
            except ValueError as exc:
                raise ValidationError({name: "Use YYYY-MM-DD."}) from exc
        return d("from", today.replace(day=1)), d("to", today)

    def _section(self, request, required=False):
        sid = request.query_params.get("section")
        if not sid:
            if required:
                raise ValidationError({"section": "Required."})
            return None
        s = Section.objects.filter(pk=sid, branch_id__in=resolve_scope(request).branch_ids).first()
        if s is None:
            raise ValidationError({"section": "Not found."})
        return s

    @extend_schema(parameters=[OpenApiParameter("from", str), OpenApiParameter("to", str), OpenApiParameter("section", int)],
                   responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def submissions(self, request):
        start, end = self._range(request)
        section = self._section(request)
        if section is not None and request.query_params.get("by") == "student":
            return Response(services.student_rates(section=section, start=start, end=end))
        return Response(services.submission_rates(branch=self.active_branch(), start=start, end=end, section=section))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def pending(self, request):
        return Response(services.pending(branch=self.active_branch()))

    @extend_schema(parameters=[OpenApiParameter("section", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def tests(self, request):
        return Response(services.test_scores(branch=self.active_branch(), section=self._section(request)))


