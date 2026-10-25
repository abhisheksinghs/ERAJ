from rest_framework import serializers

from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.people.models import Section, Staff, TeachingAssignment
from apps.timetable.models import BellSchedule, PeriodSlot, Room, Substitution, TeacherAbsence, TeacherLoad, TimetableEntry


class PeriodSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = PeriodSlot
        fields = ("id", "number", "label", "start", "end", "is_break", "days")

    def validate_days(self, value):
        parts = [p.strip() for p in str(value).split(",") if p.strip()]
        if not parts or any(not p.isdigit() or int(p) > 6 for p in parts):
            raise serializers.ValidationError("Weekday numbers 0 (Mon) to 6 (Sun), comma separated.")
        return ",".join(parts)

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": "Ends before it starts."})
        return attrs


class BellScheduleSerializer(BranchScopedSerializer):
    slots = PeriodSlotSerializer(many=True)
    sections = ScopedPrimaryKeyRelatedField(queryset=Section.objects.all(), many=True, required=False)

    class Meta:
        model = BellSchedule
        fields = ("id", "branch", "name", "is_default", "sections", "slots")

    def validate_slots(self, slots):
        numbers = [s["number"] for s in slots]
        if len(numbers) != len(set(numbers)):
            raise serializers.ValidationError("Each period number once.")
        return slots

    def _save_slots(self, schedule, slots):
        if slots is None:
            return
        keep = {s["number"]: s for s in slots}
        if schedule.slots.exclude(number__in=keep).filter(entries__isnull=False).exists():
            raise serializers.ValidationError({"slots": "A period with lessons on the timetable cannot be removed."})
        schedule.slots.exclude(number__in=keep).delete()
        for number, data in keep.items():
            data = {k: v for k, v in data.items() if k != "id"}
            PeriodSlot.objects.update_or_create(schedule=schedule, number=number, defaults=data)

    def create(self, validated_data):
        slots = validated_data.pop("slots")
        schedule = super().create(validated_data)
        self._save_slots(schedule, slots)
        return schedule

    def update(self, instance, validated_data):
        slots = validated_data.pop("slots", None)
        schedule = super().update(instance, validated_data)
        self._save_slots(schedule, slots)
        return schedule


class ClassroomSerializer(BranchScopedSerializer):
    class Meta:
        model = Room
        fields = ("id", "branch", "name", "capacity", "kind")


class TeacherLoadSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)

    class Meta:
        model = TeacherLoad
        fields = ("id", "branch", "staff", "staff_name", "max_periods_per_week")


class TimetableEntrySerializer(BranchScopedSerializer):
    subject = serializers.CharField(source="assignment.subject.name", read_only=True)
    teacher = serializers.CharField(source="assignment.staff.full_name", read_only=True)
    section_name = serializers.CharField(source="section.__str__", read_only=True)
    slot_label = serializers.CharField(source="slot.label", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True, default=None)
    slot = serializers.PrimaryKeyRelatedField(queryset=PeriodSlot.objects.all())
    assignment = ScopedPrimaryKeyRelatedField(queryset=TeachingAssignment.objects.select_related("subject", "staff"))
    room = ScopedPrimaryKeyRelatedField(queryset=Room.objects.all(), required=False, allow_null=True)

    class Meta:
        model = TimetableEntry
        fields = ("id", "branch", "section", "section_name", "day", "slot", "slot_label", "assignment", "subject", "teacher",
                  "room", "room_name")

    def validate_slot(self, slot):
        request = self.context.get("request")
        from apps.org.scope import resolve_scope

        if request is not None and slot.schedule.branch_id not in resolve_scope(request).branch_ids:
            raise serializers.ValidationError("Not found.")
        return slot


class TeacherAbsenceSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)

    class Meta:
        model = TeacherAbsence
        fields = ("id", "branch", "staff", "staff_name", "date", "reason")


class SubstitutionSerializer(BranchScopedSerializer):
    section_name = serializers.CharField(source="entry.section.__str__", read_only=True)
    slot = serializers.CharField(source="entry.slot.label", read_only=True)
    subject = serializers.CharField(source="entry.assignment.subject.name", read_only=True)
    absent_name = serializers.CharField(source="absent_staff.full_name", read_only=True)
    substitute_name = serializers.CharField(source="substitute.full_name", read_only=True)

    class Meta:
        model = Substitution
        fields = ("id", "branch", "date", "entry", "section_name", "slot", "subject", "absent_staff", "absent_name",
                  "substitute", "substitute_name", "confirmed_by", "note")
        read_only_fields = fields


class ConfirmSerializer(serializers.Serializer):
    entry = ScopedPrimaryKeyRelatedField(queryset=TimetableEntry.objects.select_related("slot", "assignment__staff", "assignment__subject"))
    date = serializers.DateField()
    substitute = ScopedPrimaryKeyRelatedField(queryset=Staff.objects.all())
    note = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
