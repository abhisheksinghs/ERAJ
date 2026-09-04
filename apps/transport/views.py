from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import RolePermission
from apps.transport import services
from apps.transport.models import Route, TransportAssignment, Vehicle
from apps.transport.serializers import (
    AssignSerializer,
    RouteSerializer,
    TransportAssignmentSerializer,
    VehicleSerializer,
)


class RouteViewSet(viewsets.ModelViewSet):
    queryset = Route.objects.all()
    serializer_class = RouteSerializer
    permission_classes = [RolePermission]
    search_fields = ["name"]


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.select_related("route").all()
    serializer_class = VehicleSerializer
    permission_classes = [RolePermission]
    filterset_fields = ["route"]
    search_fields = ["number"]


class TransportAssignmentViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = TransportAssignment.objects.select_related("vehicle").all()
    serializer_class = TransportAssignmentSerializer
    permission_classes = [RolePermission]
    filterset_fields = ["vehicle"]
    ordering_fields = ["created_at"]

    def create(self, request, *args, **kwargs):
        data = AssignSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        assignment = services.assign(**data.validated_data)
        return Response(TransportAssignmentSerializer(assignment).data, status=201)

    @action(detail=True, methods=["post"])
    def unassign(self, request, pk=None):
        return Response(TransportAssignmentSerializer(services.unassign(assignment=self.get_object())).data)
