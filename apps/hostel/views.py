from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import Conflict
from apps.hostel import services
from apps.hostel.filters import AllocationFilter, RoomFilter
from apps.hostel.models import Allocation, MaintenanceTicket, Room, Waitlist
from apps.org.mixins import BranchScopedViewSetMixin
from apps.hostel.serializers import (
    AllocationCreateSerializer,
    AllocationSerializer,
    MaintenanceTicketSerializer,
    OccupancySerializer,
    RoomSerializer,
    WaitlistSerializer,
)


class RoomViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    perm_resource = "hostel.room"
    filterset_class = RoomFilter
    search_fields = ["number"]
    ordering_fields = ["number", "floor", "capacity"]

    @action(detail=False, methods=["get"])
    def occupancy(self, request):
        rows = [
            {
                "room": r.number,
                "room_type": r.room_type,
                "capacity": r.capacity,
                "occupied": r.occupied,
                "available_beds": r.available_beds,
            }
            for r in self.filter_queryset(self.get_queryset())
        ]
        return Response(OccupancySerializer(rows, many=True).data)


class AllocationViewSet(
    BranchScopedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Allocation.objects.select_related("student", "room").all()
    perm_resource = "hostel.allocation"
    action_perms = {"vacate": "hostel.allocation.vacate"}
    filterset_class = AllocationFilter
    ordering_fields = ["check_in_date", "created_at"]

    def get_serializer_class(self):
        return AllocationCreateSerializer if self.action == "create" else AllocationSerializer

    def create(self, request, *args, **kwargs):
        data = AllocationCreateSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        alloc = services.allocate(**data.validated_data)
        return Response(AllocationSerializer(alloc).data, status=201)

    @action(detail=True, methods=["post"])
    def vacate(self, request, pk=None):
        return Response(AllocationSerializer(services.vacate(allocation=self.get_object())).data)


class WaitlistViewSet(
    BranchScopedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Waitlist.objects.select_related("student", "room").all()
    serializer_class = WaitlistSerializer
    perm_resource = "hostel.waitlist"
    filterset_fields = ["student", "room", "status"]

    def perform_create(self, serializer):
        room = serializer.validated_data["room"]
        student = serializer.validated_data["student"]
        if room.available_beds > 0:
            raise Conflict("Room has space — allocate directly instead of waitlisting.")
        if Waitlist.objects.filter(
            room=room, student=student,
            status__in=[Waitlist.Status.WAITING, Waitlist.Status.OFFERED],
        ).exists():
            raise Conflict("Student is already on this room's waitlist.")
        super().perform_create(serializer)

    def perform_destroy(self, instance):
        instance.status = Waitlist.Status.CANCELLED
        instance.save(update_fields=["status", "updated_at"])


class MaintenanceTicketViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = MaintenanceTicket.objects.select_related("room").all()
    serializer_class = MaintenanceTicketSerializer
    perm_resource = "hostel.maintenance"
    action_perms = {"close": "hostel.maintenance.manage"}
    filterset_fields = ["room", "status"]
    http_method_names = ["get", "post", "head", "options"]  # close via the action, not PUT

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return Response(
            MaintenanceTicketSerializer(services.close_ticket(ticket=self.get_object())).data
        )
