from rest_framework import serializers

from apps.hostel.models import Allocation, MaintenanceTicket, Room, Waitlist
from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.people.models import Student


class RoomSerializer(BranchScopedSerializer):
    occupied = serializers.IntegerField(read_only=True)
    available_beds = serializers.IntegerField(read_only=True)

    class Meta:
        model = Room
        fields = (
            "id", "branch", "number", "capacity", "room_type", "gender", "floor", "status",
            "occupied", "available_beds", "created_at",
        )


class AllocationSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)
    room_number = serializers.CharField(source="room.number", read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Allocation
        fields = (
            "id", "branch", "student", "student_name", "admission_no", "room", "room_number",
            "check_in_date", "check_out_date", "is_active", "created_at",
        )
        read_only_fields = ("student", "room", "check_in_date", "check_out_date", "created_at")


class AllocationCreateSerializer(serializers.Serializer):
    student = ScopedPrimaryKeyRelatedField(queryset=Student.objects.all())
    room = ScopedPrimaryKeyRelatedField(queryset=Room.objects.all())


class WaitlistSerializer(BranchScopedSerializer):
    class Meta:
        model = Waitlist
        fields = ("id", "branch", "student", "room", "status", "created_at")
        read_only_fields = ("status",)


class MaintenanceTicketSerializer(BranchScopedSerializer):
    class Meta:
        model = MaintenanceTicket
        fields = ("id", "branch", "room", "summary", "details", "status", "closed_at", "created_at")
        read_only_fields = ("status", "closed_at")


class OccupancySerializer(serializers.Serializer):
    room = serializers.CharField()
    room_type = serializers.CharField()
    capacity = serializers.IntegerField()
    occupied = serializers.IntegerField()
    available_beds = serializers.IntegerField()
