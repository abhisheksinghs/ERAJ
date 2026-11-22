from datetime import date

from django.http import FileResponse, HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.exceptions import Conflict
from apps.hr import services
from apps.hr.models import Designation, LeaveApplication, LeaveBalance, LeaveType, StaffAttendance, StaffDocument, StaffProfile
from apps.hr.serializers import (
    LeaveDecisionSerializer, DesignationSerializer, ExitSerializer, HRStaffSerializer, LeaveApplicationSerializer,
    LeaveBalanceSerializer, LeaveTypeSerializer, MarkDaySerializer, SelfLeaveSerializer, StaffAttendanceSerializer,
    StaffDocumentSerializer, StaffProfileSerializer,
)
from apps.org.mixins import BranchScopedViewSetMixin
from apps.org.permissions import request_can
from apps.people.models import Department, Staff, staff_for_user


def who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


def qdate(request, name="date", default=None) -> date:
    raw = request.query_params.get(name)
    if not raw:
        if default is None:
            raise ValidationError({name: "Required (YYYY-MM-DD)."})
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({name: "Use YYYY-MM-DD."}) from exc


def qmonth(request, name="month") -> date:
    raw = request.query_params.get(name)
    if not raw:
        return timezone.localdate().replace(day=1)
    try:
        return date.fromisoformat(f"{raw[:7]}-01")
    except ValueError as exc:
        raise ValidationError({name: "Use YYYY-MM."}) from exc


class DesignationViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Designation.objects.all()
    serializer_class = DesignationSerializer
    perm_resource = "hr.designation"
    search_fields = ["name"]


class StaffProfileViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = StaffProfile.objects.select_related("staff")
    serializer_class = StaffProfileSerializer
    perm_resource = "hr.profile"
    filterset_fields = ["staff"]
    search_fields = ["staff__full_name", "staff__employee_code", "pan", "uan"]


class StaffDocumentViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                           mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = StaffDocument.objects.select_related("staff")
    serializer_class = StaffDocumentSerializer
    perm_resource = "hr.document"
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ["staff", "kind"]

    def perform_create(self, serializer):
        from apps.core.audit import record

        doc = serializer.save(branch=self.active_branch(), uploaded_by=who(self.request))
        record("hr.document.uploaded", actor=who(self.request), staff=doc.staff_id, document=doc.pk, kind=doc.kind)

    def perform_destroy(self, instance):
        from apps.core.audit import record

        record("hr.document.deleted", actor=who(self.request), staff=instance.staff_id, document=instance.pk)
        instance.file.delete(save=False)
        instance.delete()

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        doc = self.get_object()
        resp = FileResponse(doc.file.open("rb"), content_type=doc.content_type or "application/octet-stream")
        resp["Content-Disposition"] = f'attachment; filename="{doc.original_name or "document"}"'
        resp["X-Content-Type-Options"] = "nosniff"
        return resp


class StaffAttendanceViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Daily staff attendance (one save per date), monthly register (?pdf=1), punches → present."""

    queryset = StaffAttendance.objects.select_related("staff")
    serializer_class = StaffAttendanceSerializer
    perm_resource = "hr.attendance"
    action_perms = {"mark": "hr.attendance.manage"}
    filterset_fields = {"staff": ["exact"], "date": ["exact", "gte", "lte"], "status": ["exact"]}

    @extend_schema(parameters=[OpenApiParameter("date", str)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def day(self, request):
        return Response(services.day_sheet(branch=self.active_branch(), on=qdate(request, default=timezone.localdate())))

    @extend_schema(request=MarkDaySerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def mark(self, request):
        s = MarkDaySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        r = services.mark_day(branch=self.active_branch(), on=v["date"], statuses=v["statuses"], absent=v["absent"],
                              by=who(request), can_correct_past=request_can(request, "hr.attendance.correct_past"))
        return Response(r.__dict__)

    @extend_schema(parameters=[OpenApiParameter("month", str), OpenApiParameter("department", int),
                               OpenApiParameter("pdf", bool)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def register(self, request):
        branch = self.active_branch()
        dept = None
        if request.query_params.get("department"):
            dept = Department.objects.filter(pk=request.query_params["department"], branch=branch).first()
            if dept is None:
                raise ValidationError({"department": "Not found."})
        data = services.register(branch=branch, month=qmonth(request), department=dept)
        if not request.query_params.get("pdf"):
            return Response(data)
        from apps.hr.pdf import register_pdf

        resp = HttpResponse(register_pdf(data, branch=branch), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="staff-register-{data["month"]:%Y-%m}.pdf"'
        return resp


class LeaveTypeViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    perm_resource = "hr.leavetype"


class LeaveBalanceViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = LeaveBalance.objects.select_related("staff", "leave_type")
    serializer_class = LeaveBalanceSerializer
    perm_resource = "hr.balance"
    action_perms = {"open_year": "hr.balance.manage"}
    filterset_fields = ["staff", "leave_type", "year"]

    def perform_update(self, serializer):
        from apps.core.audit import record

        old = serializer.instance.entitled
        b = serializer.save()
        record("hr.leave.balance_adjusted", actor=who(self.request), balance=b.pk, old=str(old), new=str(b.entitled))

    @extend_schema(request=None, parameters=[OpenApiParameter("year", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"], url_path="open-year")
    def open_year(self, request):
        year = int(request.data.get("year") or timezone.localdate().year)
        n = services.open_year(branch=self.active_branch(), year=year, by=who(request))
        return Response({"year": year, "created": n})


class LeaveApplicationViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                              mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = LeaveApplication.objects.select_related("staff", "leave_type")
    serializer_class = LeaveApplicationSerializer
    perm_resource = "hr.leave"
    action_perms = {"approve": "hr.leave.approve", "reject": "hr.leave.approve", "cancel": "hr.leave.manage"}
    filterset_fields = ["staff", "leave_type", "status"]
    search_fields = ["staff__full_name", "staff__employee_code"]

    def perform_create(self, serializer):
        v = serializer.validated_data
        serializer.instance = services.apply_leave(staff=v["staff"], leave_type=v["leave_type"], start=v["start"],
                                                   end=v["end"], half_day=v.get("half_day", False),
                                                   reason=v.get("reason", ""), by=who(self.request))

    def _decide(self, request, fn):
        s = LeaveDecisionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        app = fn(application=self.get_object(), by=who(request), remarks=s.validated_data["remarks"])
        return Response(LeaveApplicationSerializer(app, context={"request": request}).data)

    @extend_schema(request=LeaveDecisionSerializer, responses=LeaveApplicationSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, services.approve_leave)

    @extend_schema(request=LeaveDecisionSerializer, responses=LeaveApplicationSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, services.reject_leave)

    @extend_schema(request=None, responses=LeaveApplicationSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        app = services.cancel_leave(application=self.get_object(), by=who(request),
                                    may_cancel_approved=request_can(request, "hr.leave.approve"))
        return Response(LeaveApplicationSerializer(app, context={"request": request}).data)


class HRStaffViewSet(BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Staff as HR sees them (with joining/exit details); `exit` marks a staff member as left."""

    queryset = Staff.objects.select_related("department", "hr_profile")
    serializer_class = HRStaffSerializer
    perm_resource = "hr.profile"
    action_perms = {"exit": "hr.exit.manage"}
    filterset_fields = ["department", "employment_type"]
    search_fields = ["full_name", "employee_code"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(services.directory_filter(self.request.query_params)) if self.action == "list" else qs

    @extend_schema(request=ExitSerializer, responses=HRStaffSerializer)
    @action(detail=True, methods=["post"])
    def exit(self, request, pk=None):
        s = ExitSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        staff = services.exit_staff(staff=self.get_object(), relieved_on=s.validated_data["relieved_on"],
                                    reason=s.validated_data["reason"], by=who(request))
        return Response(HRStaffSerializer(Staff.objects.select_related("department", "hr_profile").get(pk=staff.pk)).data)


class HRReportViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    perm_resource = "hr.report"
    queryset = Staff.objects.none()

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def headcount(self, request):
        return Response(services.headcount(branch=self.active_branch()))

    @extend_schema(parameters=[OpenApiParameter("year", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def balances(self, request):
        year = int(request.query_params.get("year") or timezone.localdate().year)
        return Response(services.balances_report(branch=self.active_branch(), year=year))

    @extend_schema(parameters=[OpenApiParameter("date", str)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def absentees(self, request):
        return Response(services.absentees(branch=self.active_branch(), on=qdate(request, default=timezone.localdate())))


class MyHRViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    """Self-service for any staff login: own balances and leave, apply, cancel pending."""

    perm_resource = "hr.self"
    action_perms = {"apply": "hr.self.apply", "cancel": "hr.self.apply"}
    queryset = LeaveApplication.objects.none()

    def _me(self, request):
        me = staff_for_user(request.user)
        if me is None:
            raise NotFound("Your login isn't linked to a staff record.")
        return me

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def summary(self, request):
        me = self._me(request)
        year = timezone.localdate().year
        for lt in LeaveType.objects.filter(branch=me.branch, annual_days__isnull=False):
            services.balance_for(staff=me, leave_type=lt, year=year)
        bals = LeaveBalance.objects.filter(staff=me, year=year).select_related("leave_type", "staff")
        apps = LeaveApplication.objects.filter(staff=me).select_related("leave_type", "staff")[:50]
        ctx = {"request": request}
        return Response({
            "staff": me.pk, "name": me.full_name, "employee_code": me.employee_code, "year": year,
            "leave_types": LeaveTypeSerializer(LeaveType.objects.filter(branch=me.branch), many=True, context=ctx).data,
            "balances": LeaveBalanceSerializer(bals, many=True, context=ctx).data,
            "applications": LeaveApplicationSerializer(apps, many=True, context=ctx).data,
        })

    @extend_schema(request=SelfLeaveSerializer, responses=LeaveApplicationSerializer)
    @action(detail=False, methods=["post"])
    def apply(self, request):
        me = self._me(request)
        s = SelfLeaveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        lt = LeaveType.objects.filter(pk=v["leave_type"], branch=me.branch).first()
        if lt is None:
            raise ValidationError({"leave_type": "Not found."})
        app = services.apply_leave(staff=me, leave_type=lt, start=v["start"], end=v["end"], half_day=v["half_day"],
                                   reason=v["reason"], by=who(request))
        return Response(LeaveApplicationSerializer(app, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=LeaveApplicationSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        me = self._me(request)
        app = LeaveApplication.objects.filter(pk=pk, staff=me).first()
        if app is None:
            raise NotFound()
        if app.status != LeaveApplication.Status.PENDING:
            raise Conflict("Only a pending application can be withdrawn; ask HR to cancel approved leave.")
        app = services.cancel_leave(application=app, by=who(request), may_cancel_approved=False)
        return Response(LeaveApplicationSerializer(app, context={"request": request}).data)
