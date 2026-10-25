from django.db.models import Count, Prefetch, Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.org.mixins import BranchScopedViewSetMixin, PermissionedViewSetMixin
from apps.people import imports
from apps.people.models import (
    AcademicYear,
    Department,
    Enrollment,
    Guardian,
    Program,
    Section,
    Staff,
    Student,
    StudentGuardian,
    Subject,
    Term,
)
from apps.people.serializers import (
    AcademicYearSerializer,
    DepartmentSerializer,
    EnrollmentSerializer,
    GuardianSerializer,
    ImportResultSerializer,
    ProgramSerializer,
    SectionSerializer,
    StaffSerializer,
    StudentGuardianSerializer,
    StudentSerializer,
    SubjectSerializer,
    TermSerializer,
)


class AcademicYearViewSet(PermissionedViewSetMixin, viewsets.ModelViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    perm_resource = "people.academic_year"

    def perform_create(self, serializer):
        self._save(serializer)

    def perform_update(self, serializer):
        self._save(serializer)

    @staticmethod
    def _save(serializer):
        # Only one current year: unset the old one in the same transaction.
        if serializer.validated_data.get("is_current"):
            AcademicYear.objects.filter(is_current=True).exclude(pk=getattr(serializer.instance, "pk", None)).update(
                is_current=False
            )
        serializer.save()


class DepartmentViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    perm_resource = "people.department"
    search_fields = ["name"]


class ProgramViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Program.objects.all()
    serializer_class = ProgramSerializer
    perm_resource = "people.program"
    filterset_fields = ["kind"]
    search_fields = ["name", "code"]


class TermViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Term.objects.select_related("program")
    serializer_class = TermSerializer
    perm_resource = "people.term"
    filterset_fields = ["program"]


class SubjectViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    perm_resource = "people.subject"
    filterset_fields = ["program", "term"]
    search_fields = ["name", "code"]


class SectionViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = SectionSerializer
    perm_resource = "people.section"
    filterset_fields = ["academic_year", "program", "term"]
    search_fields = ["name", "program__name"]

    def get_queryset(self):
        base = Section.objects.select_related("program", "class_teacher").annotate(
            student_count=Count("enrollments", filter=Q(enrollments__status=Enrollment.Status.ACTIVE))
        )
        self.queryset = base
        return super().get_queryset()


class StaffViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Staff.objects.select_related("department")
    serializer_class = StaffSerializer
    perm_resource = "people.staff"
    action_perms = {"import_file": "people.staff.manage"}
    filterset_fields = ["department", "status", "employment_type"]
    search_fields = ["full_name", "employee_code", "phone", "email"]
    ordering_fields = ["full_name", "employee_code", "date_joined"]

    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser, FormParser])
    def import_file(self, request):
        return _run_import(request, imports.import_staff, self.active_branch())


class StudentViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = StudentSerializer
    perm_resource = "people.student"
    action_perms = {"import_file": "people.student.manage"}
    filterset_fields = ["status", "gender"]
    search_fields = ["full_name", "admission_no", "phone", "guardian_links__guardian__phone"]
    ordering_fields = ["full_name", "admission_no", "admission_date"]

    def get_queryset(self):
        self.queryset = Student.objects.prefetch_related(
            Prefetch("guardian_links", queryset=StudentGuardian.objects.select_related("guardian"))
        )
        qs = super().get_queryset()
        p = self.request.query_params
        current = Q(enrollments__academic_year__is_current=True, enrollments__status=Enrollment.Status.ACTIVE)
        if p.get("program"):
            qs = qs.filter(current, enrollments__program_id=p["program"])
        if p.get("section"):
            qs = qs.filter(current, enrollments__section_id=p["section"])
        return qs.distinct()

    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser, FormParser])
    def import_file(self, request):
        return _run_import(request, imports.import_students, self.active_branch())


class GuardianViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Guardian.objects.all()
    serializer_class = GuardianSerializer
    perm_resource = "people.guardian"
    search_fields = ["full_name", "phone"]


class StudentGuardianViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = StudentGuardian.objects.select_related("guardian")
    serializer_class = StudentGuardianSerializer
    perm_resource = "people.guardian"
    filterset_fields = ["student", "guardian"]

    def perform_create(self, serializer):
        if serializer.validated_data.get("is_primary"):
            StudentGuardian.objects.filter(student=serializer.validated_data["student"], is_primary=True).update(
                is_primary=False
            )
        super().perform_create(serializer)


class EnrollmentViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Enrollment.objects.select_related("student", "program", "section")
    serializer_class = EnrollmentSerializer
    perm_resource = "people.enrollment"
    filterset_fields = ["academic_year", "program", "term", "section", "status", "student"]
    search_fields = ["student__full_name", "student__admission_no", "roll_no"]


def _run_import(request, importer, branch):
    upload = request.FILES.get("file")
    if upload is None:
        raise ValidationError({"file": "Attach an .xlsx or .csv file."})
    dry_run = str(request.data.get("dry_run", "false")).lower() in ("1", "true", "yes")
    try:
        rows = imports.read_rows(upload)
    except imports.ImportFileError as exc:
        raise ValidationError({"file": str(exc)}) from exc
    result = importer(branch=branch, rows=rows, dry_run=dry_run)
    status = 400 if result["errors"] else (200 if result["dry_run"] else 201)
    return Response(ImportResultSerializer(result).data, status=status)
