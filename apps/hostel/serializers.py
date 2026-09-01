from rest_framework import serializers

from apps.hostel.models import Allocation, MaintenanceTicket, Resident, Room, Waitlist


class RoomSerializer(serializers.ModelSerializer):
    occupied = serializers.IntegerField(read_only=True)
    available_beds = serializers.IntegerField(read_only=True)

    class Meta:
        model = Room
        fields = (
            "id", "number", "capacity", "room_type", "gender", "floor", "status",
            "occupied", "available_beds", "created_at",
        )


class ResidentSerializer(serializers.ModelSerializer):
    current_room = serializers.SerializerMethodField()

    class Meta:
        model = Resident
        fields = (
            "id", "full_name", "email", "phone", "guardian_name", "guardian_phone",
            "current_room", "created_at",
        )

    def get_current_room(self, obj):
        alloc = obj.current_allocation
        return alloc.room.number if alloc else None


class AllocationSerializer(serializers.ModelSerializer):
    resident_name = serializers.CharField(source="resident.full_name", read_only=True)
    room_number = serializers.CharField(source="room.number", read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Allocation
        fields = (
            "id", "resident", "resident_name", "room", "room_number",
            "check_in_date", "check_out_date", "is_active", "created_at",
        )
        read_only_fields = ("resident", "room", "check_in_date", "check_out_date", "created_at")


class AllocationCreateSerializer(serializers.Serializer):
    resident = serializers.PrimaryKeyRelatedField(queryset=Resident.objects.all())
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all())


class WaitlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Waitlist
        fields = ("id", "resident", "room", "status", "created_at")
        read_only_fields = ("status",)


class MaintenanceTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceTicket
        fields = ("id", "room", "summary", "details", "status", "closed_at", "created_at")
        read_only_fields = ("status", "closed_at")


class OccupancySerializer(serializers.Serializer):
    room = serializers.CharField()
    room_type = serializers.CharField()
    capacity = serializers.IntegerField()
    occupied = serializers.IntegerField()
    available_beds = serializers.IntegerField()
