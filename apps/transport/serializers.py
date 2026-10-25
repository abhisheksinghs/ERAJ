from rest_framework import serializers

from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.transport.models import Route, TransportAssignment, Vehicle


class RouteSerializer(BranchScopedSerializer):
    class Meta:
        model = Route
        fields = ("id", "branch", "name", "stops")


class VehicleSerializer(BranchScopedSerializer):
    route_name = serializers.CharField(source="route.name", read_only=True, default=None)
    active_riders = serializers.IntegerField(read_only=True)
    available_seats = serializers.IntegerField(read_only=True)

    class Meta:
        model = Vehicle
        fields = (
            "id", "branch", "number", "capacity", "route", "route_name",
            "active_riders", "available_seats", "created_at",
        )
        read_only_fields = ("created_at",)


class TransportAssignmentSerializer(BranchScopedSerializer):
    class Meta:
        model = TransportAssignment
        fields = (
            "id", "branch", "vehicle", "rider_name", "rider_contact", "pickup_point",
            "removed_at", "created_at",
        )
        read_only_fields = ("removed_at", "created_at")


class AssignSerializer(serializers.Serializer):
    vehicle = ScopedPrimaryKeyRelatedField(queryset=Vehicle.objects.all())
    rider_name = serializers.CharField(max_length=255)
    rider_contact = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    pickup_point = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
