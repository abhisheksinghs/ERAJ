from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.org.mixins import BranchScopedViewSetMixin
from apps.org.scope import resolve_scope
from apps.people.models import Section, Staff
from apps.timetable import services
from apps.timetable.models import BellSchedule, Room, Substitution, TeacherAbsence, TeacherLoad, TimetableEntry
from apps.timetable.serializers import (
    BellScheduleSerializer, ConfirmSerializer, ClassroomSerializer, SubstitutionSerializer, TeacherAbsenceSerializer,
    TeacherLoadSerializer, TimetableEntrySerializer,
)


def _who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


def _date(request, name="date", default=None) -> date:
    raw = request.query_params.get(name)
    if not raw:
        if default is None:
            raise ValidationError({name: "Required (YYYY-MM-DD)."})
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({name: "Use YYYY-MM-DD."}) from exc


def _get(request, model, name, required=True):
    raw = request.query_params.get(name)
    if not raw:
        if required:
            raise ValidationError({name: "Required."})
        return None
    obj = model.objects.filter(pk=raw, branch_id__in=resolve_scope(request).branch_ids).first()
    if obj is None:
        raise ValidationError({name: "Not found."})
    return obj


def _maybe_pdf(request, grid: dict, branch, name: str):
    if not request.query_params.get("pdf"):
        return Response(grid)
    from apps.timetable.pdf import grid_pdf

    resp = HttpResponse(grid_pdf(grid, branch=branch), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="timetable-{name}.pdf"'
    return resp


class BellScheduleViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = BellSchedule.objects.prefetch_related("slots", "sections")
    serializer_class = BellScheduleSerializer
    perm_resource = "timetable.schedule"


class RoomViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = ClassroomSerializer
    perm_resource = "timetable.room"
    search_fields = ["name"]


class TeacherLoadViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = TeacherLoad.objects.select_related("staff")
    serializer_class = TeacherLoadSerializer
    perm_resource = "timetable.load"


class TimetableEntryViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = TimetableEntry.objects.select_related("section__program", "slot", "assignment__subject", "assignment__staff", "room")
    serializer_class = TimetableEntrySerializer
    perm_resource = "timetable.entry"
    filterset_fields = ["section", "day", "slot", "room", "assignment__staff"]

    def perform_create(self, serializer):
        v = serializer.validated_data
        serializer.instance = services.place(section=v["section"], day=v["day"], slot=v["slot"], assignment=v["assignment"],
                                             room=v.get("room"), by=_who(self.request))

    def perform_update(self, serializer):
        e = serializer.instance
        v = serializer.validated_data
        serializer.instance = services.place(
            section=v.get("section", e.section), day=v.get("day", e.day), slot=v.get("slot", e.slot),
            assignment=v.get("assignment", e.assignment), room=v.get("room", e.room), entry=e, by=_who(self.request))


class TimetableViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    """Printable views by section, teacher and room (?pdf=1 for a PDF)."""

    perm_resource = "timetable.entry"
    queryset = TimetableEntry.objects.none()

    @extend_schema(parameters=[OpenApiParameter("section", int), OpenApiParameter("date", str)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def section(self, request):
        sec = _get(request, Section, "section")
        on = _date(request, default=None) if request.query_params.get("date") else None
        return _maybe_pdf(request, services.section_grid(sec, on), sec.branch, f"section-{sec.pk}")

    @extend_schema(parameters=[OpenApiParameter("staff", int), OpenApiParameter("date", str)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def teacher(self, request):
        staff = _get(request, Staff, "staff")
        on = _date(request) if request.query_params.get("date") else None
        return _maybe_pdf(request, services.teacher_grid(staff, on), staff.branch, f"teacher-{staff.pk}")

    @extend_schema(parameters=[OpenApiParameter("room", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def room(self, request):
        room = _get(request, Room, "room")
        return _maybe_pdf(request, services.room_grid(room), room.branch, f"room-{room.pk}")


class TeacherAbsenceViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = TeacherAbsence.objects.select_related("staff")
    serializer_class = TeacherAbsenceSerializer
    perm_resource = "timetable.substitution"
    filterset_fields = ["date", "staff"]


class SubstitutionViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = Substitution.objects.select_related("entry__section__program", "entry__slot", "entry__assignment__subject",
                                                   "absent_staff", "substitute")
    serializer_class = SubstitutionSerializer
    perm_resource = "timetable.substitution"
    action_perms = {"confirm": "timetable.substitution.manage"}
    filterset_fields = {"date": ["exact", "gte", "lte"], "substitute": ["exact"], "absent_staff": ["exact"]}

    @extend_schema(parameters=[OpenApiParameter("date", str)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path="to-cover")
    def to_cover(self, request):
        """The absent teachers' periods for ?date, each with suggested substitutes."""
        on = _date(request, default=timezone.localdate())
        periods = services.periods_to_cover(branch=self.active_branch(), on=on)
        for p in periods:
            entry = TimetableEntry.objects.get(pk=p["entry"])
            p["suggestions"] = services.suggest(entry=entry, on=on)[:8]
        return Response({"date": on, "periods": periods})

    @extend_schema(request=ConfirmSerializer, responses=SubstitutionSerializer)
    @action(detail=False, methods=["post"])
    def confirm(self, request):
        data = ConfirmSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        v = data.validated_data
        sub = services.confirm(entry=v["entry"], on=v["date"], substitute=v["substitute"], by=_who(request), note=v["note"])
        return Response(SubstitutionSerializer(sub).data, status=201)

    @extend_schema(parameters=[OpenApiParameter("month", str, description="YYYY-MM")], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path="register")
    def register(self, request):
        import calendar

        raw = request.query_params.get("month") or f"{timezone.localdate():%Y-%m}"
        try:
            start = date.fromisoformat(f"{raw}-01")
        except ValueError as exc:
            raise ValidationError({"month": "Use YYYY-MM."}) from exc
        end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
        data = services.register(branch=self.active_branch(), start=start, end=end)
        if request.query_params.get("pdf"):
            from apps.timetable.pdf import register_pdf

            resp = HttpResponse(register_pdf(data, branch=self.active_branch()), content_type="application/pdf")
            resp["Content-Disposition"] = f'inline; filename="substitutions-{raw}.pdf"'
            return resp
        return Response(data)
