from rest_framework import serializers

from apps.org.serializers import BranchScopedSerializer
from apps.transport.models import (
    FareSlab, Route, RouteStop, TransportAlert, TransportAssignment, TransportSettings, Vehicle, VehicleDocument,
)


class RouteStopSerializer(serializers.ModelSerializer):
    fare = serializers.SerializerMethodField()

    class Meta:
        model = RouteStop
        fields = ("id", "sequence", "name", "name_hi", "pickup_time", "drop_time", "latitude", "longitude",
                  "distance_km", "monthly_fare", "fare")

    def get_fare(self, obj) -> str | None:
        from apps.core.exceptions import Conflict
        from apps.transport.services import fare_for

        try:
            return str(fare_for(obj)) if obj.pk else None
        except Conflict:
            return None


class RouteSerializer(BranchScopedSerializer):
    stops = RouteStopSerializer(many=True)
    stop_count = serializers.SerializerMethodField()

    class Meta:
        model = Route
        fields = ("id", "branch", "code", "name", "name_hi", "stops", "stop_count")

    def get_stop_count(self, obj) -> int:
        return len(obj.stops.all())

    def validate_stops(self, stops):
        seq = [s["sequence"] for s in stops]
        if len(seq) != len(set(seq)):
            raise serializers.ValidationError("Each stop number once.")
        for s in stops:
            if (s.get("latitude") is None) != (s.get("longitude") is None):
                raise serializers.ValidationError(f"Stop {s['sequence']}: give both latitude and longitude, or neither.")
        return stops

    def _save_stops(self, route, stops):
        if stops is None:
            return
        keep = {s["sequence"] for s in stops}
        if route.stops.exclude(sequence__in=keep).filter(assignments__isnull=False).exists():
            raise serializers.ValidationError({"stops": "A stop with riders cannot be removed; move them first."})
        route.stops.exclude(sequence__in=keep).delete()
        for s in stops:
            data = {k: v for k, v in s.items() if k not in ("id", "fare")}
            RouteStop.objects.update_or_create(route=route, sequence=s["sequence"], defaults={**data, "branch": route.branch})

    def create(self, validated_data):
        stops = validated_data.pop("stops")
        route = super().create(validated_data)
        self._save_stops(route, stops)
        return route

    def update(self, instance, validated_data):
        stops = validated_data.pop("stops", None)
        route = super().update(instance, validated_data)
        self._save_stops(route, stops)
        return route


class StopChoiceSerializer(BranchScopedSerializer):
    label = serializers.SerializerMethodField()
    route_code = serializers.CharField(source="route.code", read_only=True)

    class Meta:
        model = RouteStop
        fields = ("id", "branch", "route", "route_code", "sequence", "name", "label", "latitude", "longitude",
                  "pickup_time", "drop_time")
        read_only_fields = fields

    def get_label(self, obj) -> str:
        return f"{obj.route.code} · {obj.sequence}. {obj.name}"


class FareSlabSerializer(BranchScopedSerializer):
    class Meta:
        model = FareSlab
        fields = ("id", "branch", "from_km", "to_km", "monthly_fare")

    def validate(self, attrs):
        lo = attrs.get("from_km", getattr(self.instance, "from_km", None))
        hi = attrs.get("to_km", getattr(self.instance, "to_km", None))
        if lo is not None and hi is not None and hi <= lo:
            raise serializers.ValidationError({"to_km": "Must be more than 'from'."})
        return attrs


class VehicleSerializer(BranchScopedSerializer):
    route_code = serializers.CharField(source="route.code", read_only=True, default=None)
    riders = serializers.SerializerMethodField()
    push_url = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = ("id", "branch", "registration_no", "kind", "capacity", "route", "route_code", "driver_name",
                  "driver_phone", "helper_name", "helper_phone", "gps_device_id", "gps_allowed_ips", "is_active",
                  "riders", "last_latitude", "last_longitude", "last_speed_kmph", "last_seen_at", "push_url", "gps_key")
        read_only_fields = ("last_latitude", "last_longitude", "last_speed_kmph", "last_seen_at", "gps_key")

    def get_riders(self, obj) -> int:
        from apps.transport.services import occupancy

        return occupancy(obj)

    def get_push_url(self, obj) -> str:
        return "/api/transport/gps/push/ (header X-Device-Key)"

    def validate_registration_no(self, v):
        return " ".join(v.upper().split())

    def to_representation(self, instance):
        data = super().to_representation(instance)
        view = self.context.get("view")
        if view is None or getattr(view, "action", None) != "retrieve":
            data.pop("gps_key", None)  # the push key only on the vehicle's own screen
        return data


class VehicleDocumentSerializer(BranchScopedSerializer):
    vehicle_no = serializers.CharField(source="vehicle.registration_no", read_only=True)
    days_left = serializers.SerializerMethodField()

    class Meta:
        model = VehicleDocument
        fields = ("id", "branch", "vehicle", "vehicle_no", "kind", "number", "issued_on", "expires_on", "note", "days_left")

    def get_days_left(self, obj) -> int:
        from django.utils import timezone

        return (obj.expires_on - timezone.localdate()).days


class TransportAssignmentSerializer(BranchScopedSerializer):
    rider_name = serializers.SerializerMethodField()
    rider_type = serializers.SerializerMethodField()
    route_code = serializers.CharField(source="route.code", read_only=True)
    stop_name = serializers.CharField(source="stop.name", read_only=True)
    vehicle_no = serializers.CharField(source="vehicle.registration_no", read_only=True)
    riding = serializers.SerializerMethodField()

    class Meta:
        model = TransportAssignment
        fields = ("id", "branch", "student", "staff", "rider_name", "rider_type", "route", "route_code", "stop",
                  "stop_name", "vehicle", "vehicle_no", "start_date", "end_date", "monthly_fare", "riding", "note")
        read_only_fields = ("route", "end_date", "monthly_fare")

    def get_rider_name(self, obj) -> str:
        return obj.rider.full_name

    def get_rider_type(self, obj) -> str:
        return "student" if obj.student_id else "staff"

    def get_riding(self, obj) -> bool:
        from django.utils import timezone

        return obj.end_date is None or obj.end_date >= timezone.localdate()


class StopFromSerializer(serializers.Serializer):
    from_date = serializers.DateField()


class ChangeSerializer(serializers.Serializer):
    stop = serializers.IntegerField()
    vehicle = serializers.IntegerField()
    from_date = serializers.DateField()


class TransportSettingsSerializer(BranchScopedSerializer):
    class Meta:
        model = TransportSettings
        fields = ("id", "branch", "speed_limit_kmph", "near_stop_meters", "document_remind_days")


class TransportAlertSerializer(BranchScopedSerializer):
    vehicle_no = serializers.CharField(source="vehicle.registration_no", read_only=True)
    stop_name = serializers.CharField(source="stop.name", read_only=True, default=None)

    class Meta:
        model = TransportAlert
        fields = ("id", "branch", "vehicle", "vehicle_no", "kind", "stop", "stop_name", "at", "detail", "recipients")
        read_only_fields = fields
