from datetime import date, timedelta

from django.db.models import Count, Prefetch, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.exceptions import Conflict
from apps.hostel import gate, mess as mess_services, services
from apps.hostel.dates import month_start
from apps.hostel.filters import AllocationFilter, MessMemberFilter, OutpassFilter, RoomFilter, VisitFilter
from apps.hostel.models import (
    Allocation, ApprovedVisitor, Block, GuestMeal, HostelFeeRule, MaintenanceTicket, MealCount, MenuItem, Mess,
    MessComplaint, MessLeave, MessMember, MessRebate, Outpass, Room, Visit, Waitlist,
)
from apps.hostel.serializers import (
    AllocationCreateSerializer, AllocationSerializer, ApprovedVisitorSerializer, BlockSerializer, CloseSerializer,
    ContractorBillSerializer, DecisionSerializer, EndMembershipSerializer, GuestMealSerializer, HeadcountSerializer,
    HostelFeeRuleSerializer, MaintenanceTicketSerializer, MealCountSerializer, MenuItemSerializer,
    MessComplaintSerializer, MessLeaveSerializer, MessMemberCreateSerializer, MessMemberSerializer,
    MessRebateSerializer, MessSerializer, OutpassSerializer, RoomSerializer, VacateSerializer, VisitInSerializer,
    VisitSerializer, WaitlistSerializer,
)
from apps.org.mixins import BranchScopedViewSetMixin
from apps.people.models import StudentGuardian

ACTIVE_ALLOC = Q(allocations__check_out_date__isnull=True)


def _who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


def _date(request, name: str, default: date) -> date:
    raw = request.query_params.get(name)
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({name: "Use YYYY-MM-DD."}) from exc


def _month(request) -> date:
    raw = request.query_params.get("month")
    if not raw:
        return month_start(timezone.localdate())
    try:
        return date.fromisoformat(f"{raw}-01" if len(raw) == 7 else raw).replace(day=1)
    except ValueError as exc:
        raise ValidationError({"month": "Use YYYY-MM."}) from exc


# ============================================================== hostel
class BlockViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = BlockSerializer
    perm_resource = "hostel.block"
    filterset_fields = ["gender"]
    search_fields = ["code", "name"]

    def get_queryset(self):
        live = Q(rooms__deleted_at__isnull=True)
        self.queryset = Block.objects.annotate(
            room_count=Count("rooms", filter=live, distinct=True),
            beds=Sum("rooms__capacity", filter=live),
            occupied=Count("rooms__allocations", filter=live & Q(rooms__allocations__check_out_date__isnull=True)),
        )
        return super().get_queryset()


class RoomViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = RoomSerializer
    perm_resource = "hostel.room"
    filterset_class = RoomFilter
    search_fields = ["number", "block__code", "block__name"]
    ordering_fields = ["number", "floor", "capacity"]

    def get_queryset(self):
        self.queryset = Room.objects.select_related("block").annotate(
            occupied_count=Count("allocations", filter=ACTIVE_ALLOC, distinct=True),
            open_repairs=Count("maintenance_tickets", filter=Q(maintenance_tickets__status="open"), distinct=True),
        )
        return super().get_queryset()

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def board(self, request):
        """Occupancy board: every room with its residents, filterable like the list."""
        rooms = self.filter_queryset(self.get_queryset()).prefetch_related(
            Prefetch("allocations", queryset=Allocation.objects.filter(check_out_date__isnull=True)
                     .select_related("student"), to_attr="residents")
        )
        return Response([
            {
                "id": r.pk, "label": str(r), "block": r.block_id, "block_name": r.block.name, "floor": r.floor,
                "room_type": r.room_type, "gender": r.gender, "status": r.status, "capacity": r.capacity,
                "open_repairs": r.open_repairs,
                "residents": [{"allocation": a.pk, "student": a.student_id, "name": a.student.full_name,
                               "admission_no": a.student.admission_no} for a in r.residents],
                "free": max(0, r.capacity - len(r.residents)) if r.status == Room.Status.ACTIVE and not r.open_repairs else 0,
            }
            for r in rooms
        ])


class HostelFeeRuleViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = HostelFeeRule.objects.select_related("block")
    serializer_class = HostelFeeRuleSerializer
    perm_resource = "hostel.feerule"


class AllocationViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                        mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Allocation.objects.select_related("student", "room__block").prefetch_related(
        Prefetch("student__guardian_links", queryset=StudentGuardian.objects.select_related("guardian"))
    )
    serializer_class = AllocationSerializer
    perm_resource = "hostel.allocation"
    action_perms = {"vacate": "hostel.allocation.vacate"}
    filterset_class = AllocationFilter
    search_fields = ["student__full_name", "student__admission_no", "room__number"]
    ordering_fields = ["check_in_date", "created_at"]

    def get_serializer_class(self):
        return AllocationCreateSerializer if self.action == "create" else AllocationSerializer

    def create(self, request, *args, **kwargs):
        data = AllocationCreateSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        v = data.validated_data
        alloc = services.allocate(student=v["student"], room=v["room"], on=v.get("check_in_date"), mess_plan=v.get("mess_plan"))
        return Response(AllocationSerializer(self.get_queryset().get(pk=alloc.pk)).data, status=201)

    @extend_schema(request=VacateSerializer, responses=AllocationSerializer)
    @action(detail=True, methods=["post"])
    def vacate(self, request, pk=None):
        data = VacateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.vacate(allocation=self.get_object(), on=data.validated_data.get("date"), reason=data.validated_data["reason"])
        return Response(AllocationSerializer(self.get_queryset().get(pk=pk)).data)


class WaitlistViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                      mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = Waitlist.objects.select_related("student", "room__block")
    serializer_class = WaitlistSerializer
    perm_resource = "hostel.waitlist"
    filterset_fields = ["student", "room", "status"]

    def perform_create(self, serializer):
        v = serializer.validated_data
        serializer.instance = services.add_to_waitlist(student=v["student"], room=v["room"])

    def perform_destroy(self, instance):
        instance.status = Waitlist.Status.CANCELLED
        instance.save(update_fields=["status", "updated_at"])


class MaintenanceTicketViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                               mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = MaintenanceTicket.objects.select_related("room__block")
    serializer_class = MaintenanceTicketSerializer
    perm_resource = "hostel.maintenance"
    action_perms = {"close": "hostel.maintenance.manage"}
    filterset_fields = ["room", "status"]

    @extend_schema(request=CloseSerializer, responses=MaintenanceTicketSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        data = CloseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        ticket = services.close_ticket(ticket=self.get_object(), action_taken=data.validated_data["action_taken"])
        return Response(MaintenanceTicketSerializer(ticket).data)


# ============================================================== mess
class MessViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = MessSerializer
    perm_resource = "hostel.mess"
    action_perms = {"bill": "hostel.mess.manage"}

    def get_queryset(self):
        self.queryset = Mess.objects.prefetch_related("blocks", "meal_rates").annotate(
            member_count=Count("members", filter=Q(members__end_date__isnull=True))
        )
        return super().get_queryset()

    @extend_schema(responses=HeadcountSerializer(many=True))
    @action(detail=False, methods=["get"])
    def headcount(self, request):
        """Expected plates per meal for `?date=` (default tomorrow), per mess."""
        on = _date(request, "date", timezone.localdate() + timedelta(days=1))
        return Response(HeadcountSerializer([mess_services.headcount(m, on) for m in self.get_queryset()], many=True).data)

    @extend_schema(responses=ContractorBillSerializer)
    @action(detail=True, methods=["get"], url_path="contractor-bill")
    def contractor_bill(self, request, pk=None):
        return Response(ContractorBillSerializer(mess_services.contractor_bill(self.get_object(), _month(request))).data)

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="menu-pdf")
    def menu_pdf(self, request, pk=None):
        from apps.hostel.pdf import menu_pdf

        mess = self.get_object()
        resp = HttpResponse(menu_pdf(mess, lang=request.query_params.get("lang", "en")), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="menu-{mess.pk}.pdf"'
        return resp

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def bill(self, request):
        """Run this month's mess billing now (the monthly job does it on the 1st)."""
        branch = self.active_branch()
        return Response({"charges_posted": mess_services.bill_mess_month(branch=branch)})


class MenuItemViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    perm_resource = "hostel.menu"
    filterset_fields = ["mess", "day", "meal"]
    pagination_class = None


class MessMemberViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                        mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = MessMember.objects.select_related("mess", "student", "staff")
    serializer_class = MessMemberSerializer
    perm_resource = "hostel.messmember"
    action_perms = {"end": "hostel.messmember.manage"}
    filterset_class = MessMemberFilter
    search_fields = ["student__full_name", "student__admission_no", "staff__full_name", "staff__employee_code"]

    def get_serializer_class(self):
        return MessMemberCreateSerializer if self.action == "create" else MessMemberSerializer

    def create(self, request, *args, **kwargs):
        data = MessMemberCreateSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        v = data.validated_data
        member = mess_services.enrol(mess=v["mess"], student=v.get("student"), staff=v.get("staff"), plan=v["plan"],
                                     start=v.get("start_date"))
        return Response(MessMemberSerializer(member).data, status=201)

    @extend_schema(request=EndMembershipSerializer, responses=MessMemberSerializer)
    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        data = EndMembershipSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(MessMemberSerializer(mess_services.end_membership(member=self.get_object(), on=data.validated_data.get("date"))).data)


class MessLeaveViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                       mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = MessLeave.objects.select_related("member__student", "member__staff")
    serializer_class = MessLeaveSerializer
    perm_resource = "hostel.messleave"
    filterset_fields = ["member", "member__mess"]
    search_fields = ["member__student__full_name", "member__staff__full_name"]

    def perform_create(self, serializer):
        v = serializer.validated_data
        serializer.instance = mess_services.record_leave(
            member=v["member"], from_date=v["from_date"], to_date=v["to_date"], reason=v.get("reason", "")
        )

    def perform_destroy(self, instance):
        if instance.outpass_id:
            raise Conflict("This leave comes from an outpass; cancel the outpass instead.")
        if instance.rebates.exists():
            raise Conflict("A rebate has already been given for this leave.")
        instance.delete()


class MessRebateViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Rebate register."""

    queryset = MessRebate.objects.select_related("member__student", "member__staff", "leave")
    serializer_class = MessRebateSerializer
    perm_resource = "hostel.messrebate"
    filterset_fields = ["member", "month", "member__mess"]


class GuestMealViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                       mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = GuestMeal.objects.select_related("member__student", "member__staff")
    serializer_class = GuestMealSerializer
    perm_resource = "hostel.guestmeal"
    filterset_fields = ["member", "date", "meal", "member__mess"]

    def perform_create(self, serializer):
        v = serializer.validated_data
        serializer.instance = mess_services.add_guest_meal(
            member=v["member"], meal=v["meal"], count=v.get("count", 1), on=v.get("date"), guest_name=v.get("guest_name", "")
        )


class MealCountViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = MealCount.objects.all()
    serializer_class = MealCountSerializer
    perm_resource = "hostel.mealcount"
    filterset_fields = ["mess", "date", "meal"]


class MessComplaintViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                           mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = MessComplaint.objects.select_related("mess", "member__student", "member__staff")
    serializer_class = MessComplaintSerializer
    perm_resource = "hostel.complaint"
    action_perms = {"close": "hostel.complaint.manage"}
    filterset_fields = ["mess", "status", "category"]

    @extend_schema(request=CloseSerializer, responses=MessComplaintSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        data = CloseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        c = self.get_object()
        if c.status == MessComplaint.Status.CLOSED:
            raise Conflict("Complaint already closed.")
        if not data.validated_data["action_taken"]:
            raise ValidationError({"action_taken": "Record the action taken."})
        c.status, c.action_taken = MessComplaint.Status.CLOSED, data.validated_data["action_taken"]
        c.closed_by, c.closed_at = _who(request), timezone.now()
        c.save(update_fields=["status", "action_taken", "closed_by", "closed_at", "updated_at"])
        return Response(MessComplaintSerializer(c).data)


# ============================================================== gate
class ApprovedVisitorViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ApprovedVisitor.objects.select_related("student")
    serializer_class = ApprovedVisitorSerializer
    perm_resource = "hostel.visitor"
    filterset_fields = ["student"]
    search_fields = ["name", "phone", "student__full_name", "student__admission_no"]


class VisitViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                   mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Visit.objects.select_related("student")
    serializer_class = VisitSerializer
    perm_resource = "hostel.visit"
    action_perms = {"approve": "hostel.visit.approve", "refuse": "hostel.visit.approve", "leave": "hostel.visit.manage"}
    filterset_class = VisitFilter
    search_fields = ["name", "phone", "student__full_name"]

    def get_serializer_class(self):
        return VisitInSerializer if self.action == "create" else VisitSerializer

    def create(self, request, *args, **kwargs):
        data = VisitInSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        visit = gate.visitor_arrives(**data.validated_data, by=_who(request))
        return Response(VisitSerializer(visit).data, status=201)

    @extend_schema(request=None, responses=VisitSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return Response(VisitSerializer(gate.decide_visit(visit=self.get_object(), approve=True, by=_who(request))).data)

    @extend_schema(request=None, responses=VisitSerializer)
    @action(detail=True, methods=["post"])
    def refuse(self, request, pk=None):
        return Response(VisitSerializer(gate.decide_visit(visit=self.get_object(), approve=False, by=_who(request))).data)

    @extend_schema(request=None, responses=VisitSerializer)
    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        return Response(VisitSerializer(gate.visitor_leaves(visit=self.get_object())).data)


class OutpassViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                     mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Outpass.objects.select_related("student")
    serializer_class = OutpassSerializer
    perm_resource = "hostel.outpass"
    action_perms = {
        "approve": "hostel.outpass.approve", "reject": "hostel.outpass.approve",
        "out": "hostel.outpass.gate", "back": "hostel.outpass.gate", "cancel": "hostel.outpass.manage",
    }
    filterset_class = OutpassFilter
    search_fields = ["student__full_name", "student__admission_no"]
    ordering_fields = ["from_date", "created_at"]

    def perform_create(self, serializer):
        v = serializer.validated_data
        serializer.instance = gate.request_outpass(
            student=v["student"], from_date=v["from_date"], to_date=v["to_date"], reason=v["reason"],
            destination=v.get("destination", ""), return_by=v.get("return_by"),
            requested_by=v.get("requested_by", Outpass.RequestedBy.WARDEN),
        )

    def _decide(self, request, approve: bool):
        data = DecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        op = gate.decide_outpass(outpass=self.get_object(), approve=approve, by=_who(request), note=data.validated_data["note"])
        return Response(OutpassSerializer(op).data)

    @extend_schema(request=DecisionSerializer, responses=OutpassSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decide(request, True)

    @extend_schema(request=DecisionSerializer, responses=OutpassSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decide(request, False)

    @extend_schema(request=None, responses=OutpassSerializer)
    @action(detail=True, methods=["post"])
    def out(self, request, pk=None):
        return Response(OutpassSerializer(gate.gate_out(outpass=self.get_object())).data)

    @extend_schema(request=None, responses=OutpassSerializer)
    @action(detail=True, methods=["post"])
    def back(self, request, pk=None):
        return Response(OutpassSerializer(gate.gate_in(outpass=self.get_object())).data)

    @extend_schema(request=None, responses=OutpassSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(OutpassSerializer(gate.cancel_outpass(outpass=self.get_object())).data)
