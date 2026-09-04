from rest_framework import serializers

from apps.transport.models import Route, TransportAssignment, Vehicle


class RouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Route
        fields = ("id", "name", "stops")


class VehicleSerializer(serializers.ModelSerializer):
    route_name = serializers.CharField(source="route.name", read_only=True, default=None)
    active_riders = serializers.IntegerField(read_only=True)
    available_seats = serializers.IntegerField(read_only=True)

    class Meta:
        model = Vehicle
        fields = (
            "id", "number", "capacity", "route", "route_name",
            "active_riders", "available_seats", "created_at",
        )
        read_only_fields = ("created_at",)


class TransportAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransportAssignment
        fields = (
            "id", "vehicle", "rider_name", "rider_contact", "pickup_point",
            "removed_at", "created_at",
        )
        read_only_fields = ("removed_at", "created_at")


class AssignSerializer(serializers.Serializer):
    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all())
    rider_name = serializers.CharField(max_length=255)
    rider_contact = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    pickup_point = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
