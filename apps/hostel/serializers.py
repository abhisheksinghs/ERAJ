from rest_framework import serializers

from apps.hostel.models import (
    Allocation, ApprovedVisitor, Block, GuestMeal, HostelFeeRule, MaintenanceTicket, Meal, MealCount, MenuItem, Mess,
    MessComplaint, MessLeave, MessMealRate, MessMember, MessRebate, Outpass, Room, Visit, Waitlist,
)
from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.people.models import Staff, Student

MONEY = {"max_digits": 10, "decimal_places": 2}


def _person(obj):
    p = obj.student or obj.staff
    return p.full_name if p else None


# ============================================================== hostel
class BlockSerializer(BranchScopedSerializer):
    rooms = serializers.IntegerField(source="room_count", read_only=True, default=None)
    beds = serializers.IntegerField(read_only=True, default=None)
    occupied = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = Block
        fields = ("id", "branch", "code", "name", "name_hi", "gender", "warden", "rooms", "beds", "occupied")


class RoomSerializer(BranchScopedSerializer):
    block_name = serializers.CharField(source="block.name", read_only=True)
    label = serializers.SerializerMethodField()
    occupied = serializers.IntegerField(read_only=True, source="occupied_count", default=None)
    available_beds = serializers.SerializerMethodField()
    open_repairs = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = Room
        fields = (
            "id", "branch", "block", "block_name", "number", "label", "floor", "room_type", "capacity", "gender",
            "status", "occupied", "available_beds", "open_repairs", "created_at",
        )

    def get_label(self, obj) -> str:
        return f"{obj.block.code}-{obj.number}"

    def get_available_beds(self, obj) -> int:
        occupied = getattr(obj, "occupied_count", None)
        return max(0, obj.capacity - (occupied if occupied is not None else obj.occupied))


class HostelFeeRuleSerializer(BranchScopedSerializer):
    block_name = serializers.CharField(source="block.name", read_only=True, default=None)

    class Meta:
        model = HostelFeeRule
        fields = ("id", "branch", "block", "block_name", "room_type", "monthly_amount", "is_active")


class AllocationSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)
    room_label = serializers.CharField(source="room.__str__", read_only=True)
    block_name = serializers.CharField(source="room.block.name", read_only=True)
    guardian_phone = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Allocation
        fields = (
            "id", "branch", "student", "student_name", "admission_no", "room", "room_label", "block_name",
            "guardian_phone", "check_in_date", "check_out_date", "vacate_reason", "is_active", "created_at",
        )
        read_only_fields = fields

    def get_guardian_phone(self, obj) -> str | None:
        links = list(obj.student.guardian_links.all())
        link = next((g for g in links if g.is_primary), links[0] if links else None)
        return link.guardian.phone if link else None


class AllocationCreateSerializer(serializers.Serializer):
    student = ScopedPrimaryKeyRelatedField(queryset=Student.objects.all())
    room = ScopedPrimaryKeyRelatedField(queryset=Room.objects.all())
    check_in_date = serializers.DateField(required=False)
    mess_plan = serializers.ChoiceField(choices=MessMember.Plan.choices, required=False)


class VacateSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class WaitlistSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    room_label = serializers.CharField(source="room.__str__", read_only=True)

    class Meta:
        model = Waitlist
        fields = ("id", "branch", "student", "student_name", "room", "room_label", "status", "created_at")
        read_only_fields = ("status", "created_at")


class MaintenanceTicketSerializer(BranchScopedSerializer):
    room_label = serializers.CharField(source="room.__str__", read_only=True)

    class Meta:
        model = MaintenanceTicket
        fields = ("id", "branch", "room", "room_label", "summary", "details", "status", "action_taken", "closed_at", "created_at")
        read_only_fields = ("status", "action_taken", "closed_at")


class CloseSerializer(serializers.Serializer):
    action_taken = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


# ============================================================== mess
class MessMealRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessMealRate
        fields = ("meal", "rate")


class MessSerializer(BranchScopedSerializer):
    blocks = ScopedPrimaryKeyRelatedField(queryset=Block.objects.all(), many=True, required=False)
    meal_rates = MessMealRateSerializer(many=True, required=False)
    members = serializers.IntegerField(source="member_count", read_only=True, default=None)

    class Meta:
        model = Mess
        fields = (
            "id", "branch", "name", "name_hi", "blocks", "contractor_name", "contractor_phone", "monthly_charge",
            "per_day_rate", "rebate_min_days", "rebate_per_day", "guest_meal_rate", "meal_rates", "members",
        )

    def _save_rates(self, mess, rates):
        if rates is None:
            return
        mess.meal_rates.all().delete()
        MessMealRate.objects.bulk_create([MessMealRate(mess=mess, **r) for r in rates])

    def create(self, validated_data):
        rates = validated_data.pop("meal_rates", None)
        mess = super().create(validated_data)
        self._save_rates(mess, rates)
        return mess

    def update(self, instance, validated_data):
        rates = validated_data.pop("meal_rates", None)
        mess = super().update(instance, validated_data)
        self._save_rates(mess, rates)
        return mess


class MenuItemSerializer(BranchScopedSerializer):
    class Meta:
        model = MenuItem
        fields = ("id", "branch", "mess", "day", "meal", "items", "items_hi", "is_veg")


class MessMemberSerializer(BranchScopedSerializer):
    name = serializers.SerializerMethodField()
    kind = serializers.SerializerMethodField()
    mess_name = serializers.CharField(source="mess.name", read_only=True)
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = MessMember
        fields = ("id", "branch", "mess", "mess_name", "student", "staff", "name", "kind", "plan", "start_date",
                  "end_date", "is_active", "allocation")
        read_only_fields = ("end_date", "allocation")

    def get_name(self, obj) -> str | None:
        return _person(obj)

    def get_kind(self, obj) -> str:
        return "student" if obj.student_id else "staff"

    def get_is_active(self, obj) -> bool:
        return obj.end_date is None


class MessMemberCreateSerializer(serializers.Serializer):
    mess = ScopedPrimaryKeyRelatedField(queryset=Mess.objects.all())
    student = ScopedPrimaryKeyRelatedField(queryset=Student.objects.all(), required=False, allow_null=True)
    staff = ScopedPrimaryKeyRelatedField(queryset=Staff.objects.all(), required=False, allow_null=True)
    plan = serializers.ChoiceField(choices=MessMember.Plan.choices, default=MessMember.Plan.MONTHLY)
    start_date = serializers.DateField(required=False)

    def validate(self, attrs):
        if bool(attrs.get("student")) == bool(attrs.get("staff")):
            raise serializers.ValidationError("Choose either a student or a staff member.")
        return attrs


class EndMembershipSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)


class MessLeaveSerializer(BranchScopedSerializer):
    member_name = serializers.SerializerMethodField()
    days = serializers.IntegerField(read_only=True)
    from_outpass = serializers.SerializerMethodField()

    class Meta:
        model = MessLeave
        fields = ("id", "branch", "member", "member_name", "from_date", "to_date", "days", "reason", "from_outpass", "created_at")

    def get_member_name(self, obj) -> str | None:
        return _person(obj.member)

    def get_from_outpass(self, obj) -> bool:
        return obj.outpass_id is not None


class MessRebateSerializer(BranchScopedSerializer):
    member_name = serializers.SerializerMethodField()
    leave_from = serializers.DateField(source="leave.from_date", read_only=True)
    leave_to = serializers.DateField(source="leave.to_date", read_only=True)

    class Meta:
        model = MessRebate
        fields = ("id", "branch", "member", "member_name", "month", "leave_from", "leave_to", "days", "amount", "charge")
        read_only_fields = fields

    def get_member_name(self, obj) -> str | None:
        return _person(obj.member)


class GuestMealSerializer(BranchScopedSerializer):
    member_name = serializers.SerializerMethodField()

    class Meta:
        model = GuestMeal
        fields = ("id", "branch", "member", "member_name", "date", "meal", "count", "guest_name", "amount", "charge", "created_at")
        read_only_fields = ("amount", "charge", "created_at")

    def get_member_name(self, obj) -> str | None:
        return _person(obj.member)


class MealCountSerializer(BranchScopedSerializer):
    class Meta:
        model = MealCount
        fields = ("id", "branch", "mess", "date", "meal", "served")


class MessComplaintSerializer(BranchScopedSerializer):
    member_name = serializers.SerializerMethodField()
    mess_name = serializers.CharField(source="mess.name", read_only=True)

    class Meta:
        model = MessComplaint
        fields = ("id", "branch", "mess", "mess_name", "member", "member_name", "category", "description", "status",
                  "action_taken", "closed_by", "closed_at", "created_at")
        read_only_fields = ("status", "action_taken", "closed_by", "closed_at", "created_at")

    def get_member_name(self, obj) -> str | None:
        return _person(obj.member) if obj.member else None


class HeadcountMealSerializer(serializers.Serializer):
    meal = serializers.ChoiceField(choices=Meal.choices)
    label = serializers.CharField()
    members = serializers.IntegerField()
    guests = serializers.IntegerField()
    expected = serializers.IntegerField()


class HeadcountSerializer(serializers.Serializer):
    date = serializers.DateField()
    mess = serializers.IntegerField()
    mess_name = serializers.CharField()
    enrolled = serializers.IntegerField()
    on_leave = serializers.IntegerField()
    meals = HeadcountMealSerializer(many=True)


class ContractorBillRowSerializer(serializers.Serializer):
    meal = serializers.CharField()
    label = serializers.CharField()
    plates = serializers.IntegerField()
    rate = serializers.DecimalField(**MONEY)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    estimated_days = serializers.IntegerField()


class ContractorBillSerializer(serializers.Serializer):
    mess = serializers.IntegerField()
    mess_name = serializers.CharField()
    contractor = serializers.CharField()
    month = serializers.DateField()
    rows = ContractorBillRowSerializer(many=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2)


# ============================================================== gate
class ApprovedVisitorSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = ApprovedVisitor
        fields = ("id", "branch", "student", "student_name", "name", "relation", "phone", "photo")


class VisitSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    on_approved_list = serializers.SerializerMethodField()

    class Meta:
        model = Visit
        fields = ("id", "branch", "student", "student_name", "visitor", "on_approved_list", "name", "relation", "phone",
                  "id_proof", "purpose", "status", "time_in", "time_out", "decided_by", "created_at")
        read_only_fields = ("status", "time_in", "time_out", "decided_by", "created_at")

    def get_on_approved_list(self, obj) -> bool:
        return obj.visitor_id is not None


class VisitInSerializer(serializers.Serializer):
    student = ScopedPrimaryKeyRelatedField(queryset=Student.objects.all())
    visitor = ScopedPrimaryKeyRelatedField(queryset=ApprovedVisitor.objects.all(), required=False, allow_null=True)
    name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    relation = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    id_proof = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    purpose = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if not attrs.get("visitor") and not attrs.get("name"):
            raise serializers.ValidationError({"name": "Enter the visitor's name or pick an approved visitor."})
        return attrs


class OutpassSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)
    days = serializers.IntegerField(read_only=True)

    class Meta:
        model = Outpass
        fields = ("id", "branch", "student", "student_name", "admission_no", "from_date", "to_date", "return_by", "days",
                  "destination", "reason", "requested_by", "status", "decided_by", "decision_note", "checked_out_at",
                  "checked_in_at", "is_late", "created_at")
        read_only_fields = ("status", "decided_by", "decision_note", "checked_out_at", "checked_in_at", "is_late", "created_at")


class DecisionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
