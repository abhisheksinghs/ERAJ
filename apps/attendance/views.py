from datetime import date, timedelta

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.attendance import devices, services
from apps.attendance.models import AttendanceCard, AttendanceDevice, AttendanceRecord, AttendanceSettings, Holiday, Punch
from apps.attendance.serializers import (
    AttendanceCardSerializer, AttendanceDeviceSerializer, AttendanceRecordSerializer, AttendanceSettingsSerializer,
    HolidaySerializer, MarkResultSerializer, MarkSectionSerializer, PunchImportSerializer, PunchSerializer,
    SheetSerializer, StudentPercentSerializer,
)
from apps.org.mixins import BranchScopedViewSetMixin
from apps.org.permissions import request_can
from apps.org.scope import resolve_scope
from apps.people.imports import ImportFileError, read_rows
from apps.people.models import Section, Student, staff_for_user
from apps.people.serializers import SectionSerializer


def _who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


def _date(request, name: str, default: date | None = None) -> date:
    raw = request.query_params.get(name)
    if not raw:
        if default is None:
            raise ValidationError({name: "This parameter is required (YYYY-MM-DD)."})
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({name: "Use YYYY-MM-DD."}) from exc


def _section(request, required: bool = True) -> Section | None:
    raw = request.query_params.get("section")
    if not raw:
        if required:
            raise ValidationError({"section": "This parameter is required."})
        return None
    sec = Section.objects.filter(pk=raw, branch_id__in=resolve_scope(request).branch_ids).select_related("branch").first()
    if sec is None:
        raise ValidationError({"section": "Not found."})
    return sec


def _check_section(request, section: Section, subject=None) -> None:
    if request_can(request, "attendance.record.any_section"):
        return
    if not services.may_mark_section(staff=staff_for_user(request.user), section=section, subject=subject):
        raise PermissionDenied("You can mark attendance only for your own class or the sections you teach.")


class AttendanceSettingsViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                                mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = AttendanceSettings.objects.all()
    serializer_class = AttendanceSettingsSerializer
    perm_resource = "attendance.settings"

    def list(self, request, *args, **kwargs):
        if resolve_scope(request).active is not None:
            services.settings_for(resolve_scope(request).active)
        return super().list(request, *args, **kwargs)


class HolidayViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Holiday.objects.all()
    serializer_class = HolidaySerializer
    perm_resource = "attendance.holiday"
    filterset_fields = {"date": ["gte", "lte", "exact"]}
    ordering_fields = ["date"]


class AttendanceRecordViewSet(BranchScopedViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                              viewsets.GenericViewSet):
    queryset = AttendanceRecord.objects.select_related("student", "section__program")
    serializer_class = AttendanceRecordSerializer
    perm_resource = "attendance.record"
    action_perms = {"mark": "attendance.record.mark"}
    filterset_fields = ["student", "section", "date", "status", "period", "subject", "source"]
    search_fields = ["student__full_name", "student__admission_no"]
    ordering_fields = ["date", "updated_at"]

    @extend_schema(request=MarkSectionSerializer, responses=MarkResultSerializer)
    @action(detail=False, methods=["post"])
    def mark(self, request):
        """One save for a section: everyone present except `absent` / `statuses`."""
        data = MarkSectionSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        v = data.validated_data
        _check_section(request, v["section"], v.get("subject"))
        result = services.mark_section(
            section=v["section"], on=v["date"], statuses={int(k): s for k, s in v["statuses"].items()},
            absent=v["absent"], period=v.get("period"), subject=v.get("subject"), by=_who(request),
            can_correct_past=request_can(request, "attendance.record.correct_past"),
        )
        return Response(MarkResultSerializer(result.__dict__).data)

    @extend_schema(parameters=[OpenApiParameter("section", int), OpenApiParameter("date", str), OpenApiParameter("period", int)],
                   responses=SheetSerializer)
    @action(detail=False, methods=["get"])
    def sheet(self, request):
        section = _section(request)
        _check_section(request, section)
        period = request.query_params.get("period")
        data = services.sheet(section=section, on=_date(request, "date", timezone.localdate()),
                              period=int(period) if period else None)
        return Response(SheetSerializer(data).data)

    @extend_schema(responses=SectionSerializer(many=True))
    @action(detail=False, methods=["get"], url_path="my-sections")
    def my_sections(self, request):
        """Sections the caller may mark (all current sections for Admin)."""
        today = timezone.localdate()
        qs = Section.objects.filter(branch_id__in=resolve_scope(request).branch_ids,
                                    academic_year__start_date__lte=today, academic_year__end_date__gte=today)
        if not request_can(request, "attendance.record.any_section"):
            staff = staff_for_user(request.user)
            qs = qs.filter(services.staff_in_scope_filter(staff)) if staff else qs.none()
        return Response(SectionSerializer(qs.select_related("program", "class_teacher").distinct(), many=True).data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def calendar(self, request):
        """A student's day-by-day calendar and percentage for ?student&from&to."""
        student = Student.objects.filter(pk=request.query_params.get("student"),
                                         branch_id__in=resolve_scope(request).branch_ids).first()
        if student is None:
            raise ValidationError({"student": "Not found."})
        today = timezone.localdate()
        start = _date(request, "from", today.replace(day=1))
        end = _date(request, "to", today)
        if end < start or (end - start).days > 400:
            raise ValidationError({"to": "Choose a range of up to about a year."})
        return Response(services.student_calendar(student=student, start=start, end=end))


class AttendanceReportViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    """Registers and lists. Every list also exports with ?format=xlsx / csv."""

    perm_resource = "attendance.report"
    queryset = AttendanceRecord.objects.none()

    @extend_schema(parameters=[OpenApiParameter("section", int), OpenApiParameter("month", str, description="YYYY-MM")],
                   responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def register(self, request):
        section = _section(request)
        raw = request.query_params.get("month") or f"{timezone.localdate():%Y-%m}"
        try:
            month = date.fromisoformat(f"{raw}-01")
        except ValueError as exc:
            raise ValidationError({"month": "Use YYYY-MM."}) from exc
        data = services.register(section=section, month=month)
        if request.query_params.get("pdf"):
            from apps.attendance.pdf import register_pdf

            resp = HttpResponse(register_pdf(data, branch=section.branch), content_type="application/pdf")
            resp["Content-Disposition"] = f'inline; filename="register-{section.pk}-{raw}.pdf"'
            return resp
        return Response(data)

    @extend_schema(parameters=[OpenApiParameter("date", str)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def daily(self, request):
        branch = self.active_branch()
        return Response(services.daily_summary(branch=branch, on=_date(request, "date", timezone.localdate())))

    @extend_schema(parameters=[OpenApiParameter("from", str), OpenApiParameter("to", str), OpenApiParameter("threshold", int),
                               OpenApiParameter("section", int)], responses=StudentPercentSerializer(many=True))
    @action(detail=False, methods=["get"])
    def below(self, request):
        """Students below the threshold % (default: the branch setting) in a date range."""
        branch = self.active_branch()
        cfg = services.settings_for(branch)
        today = timezone.localdate()
        start, end = _date(request, "from", today - timedelta(days=30)), _date(request, "to", today)
        threshold = float(request.query_params.get("threshold") or cfg.threshold_percent)
        one = _section(request, required=False)
        sections = [one] if one else Section.objects.filter(branch=branch, academic_year__start_date__lte=end,
                                                            academic_year__end_date__gte=start)
        rows = [r for sec in sections for r in services.section_percentages(section=sec, start=start, end=end)
                if r["marked"] and r["percentage"] < threshold]
        return Response(StudentPercentSerializer(sorted(rows, key=lambda r: r["percentage"]), many=True).data)

    @extend_schema(parameters=[OpenApiParameter("days", int), OpenApiParameter("date", str), OpenApiParameter("section", int)],
                   responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path="long-absent")
    def long_absent(self, request):
        branch = self.active_branch()
        days = int(request.query_params.get("days") or services.settings_for(branch).long_absence_days)
        return Response(services.long_absentees(branch=branch, as_of=_date(request, "date", timezone.localdate()),
                                                min_days=days, section=_section(request, required=False)))


class AttendanceDeviceViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = AttendanceDevice.objects.all()
    serializer_class = AttendanceDeviceSerializer
    perm_resource = "attendance.device"
    action_perms = {"rotate_key": "attendance.device.manage"}

    @extend_schema(request=None, responses=AttendanceDeviceSerializer)
    @action(detail=True, methods=["post"], url_path="rotate-key")
    def rotate_key(self, request, pk=None):
        from apps.attendance.models import _token

        device = self.get_object()
        device.token = _token()
        device.save(update_fields=["token", "updated_at"])
        return Response(self.get_serializer(device).data)


class AttendanceCardViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = AttendanceCard.objects.select_related("student", "staff")
    serializer_class = AttendanceCardSerializer
    perm_resource = "attendance.card"
    filterset_fields = ["student", "staff", "is_active"]
    search_fields = ["code", "student__full_name", "staff__full_name"]


class PunchViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Punch.objects.select_related("device", "student", "staff")
    serializer_class = PunchSerializer
    perm_resource = "attendance.punch"
    action_perms = {"import_file": "attendance.punch.import"}
    filterset_fields = {"device": ["exact"], "student": ["exact"], "staff": ["exact"], "source": ["exact"],
                        "punched_at": ["date", "gte", "lte"]}
    search_fields = ["code", "student__full_name", "staff__full_name"]

    @extend_schema(request={"multipart/form-data": PunchImportSerializer}, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser, FormParser])
    def import_file(self, request):
        """Import any device's punch log (Excel/CSV). Nothing is saved if a row is bad."""
        data = PunchImportSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        try:
            punches, errors = devices.rows_to_punches(read_rows(data.validated_data["file"]))
        except (ImportFileError, devices.PunchParseError) as exc:
            raise ValidationError({"file": str(exc)}) from exc
        dry_run = data.validated_data["dry_run"]
        if errors or dry_run:
            return Response({"ok": not errors, "dry_run": True, "rows": len(punches) + len(errors), "errors": errors[:200],
                             "created": 0, "saved": 0}, status=400 if errors else 200)
        result = devices.ingest(device=data.validated_data.get("device"), branch=self.active_branch(), punches=punches,
                                source=Punch.Source.IMPORT)
        return Response({"ok": True, "dry_run": False, "rows": len(punches), "errors": [], "created": result["stored"],
                         "saved": result["stored"], **result})
