from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.fees.models import (
    Charge,
    Concession,
    FeeHead,
    FeePlan,
    FeePlanInstalment,
    FeeSettings,
    Receipt,
    ReceiptLine,
    Refund,
)
from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.people.models import Student

POSITIVE = {"max_digits": 12, "decimal_places": 2, "min_value": Decimal("0.01")}


class FeeSettingsSerializer(BranchScopedSerializer):
    class Meta:
        model = FeeSettings
        fields = ("id", "branch", "receipt_prefix", "cash_ledger", "bank_ledger", "tally_company")


class FeeHeadSerializer(BranchScopedSerializer):
    class Meta:
        model = FeeHead
        fields = (
            "id", "branch", "code", "name", "name_hi", "kind", "late_fine_mode", "late_fine_amount",
            "grace_days", "tally_ledger", "is_active",
        )


class InstalmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeePlanInstalment
        fields = ("id", "sequence", "label", "due_date", "amount")


class FeePlanSerializer(BranchScopedSerializer):
    instalments = InstalmentSerializer(many=True)
    head_name = serializers.CharField(source="head.name", read_only=True)
    program_name = serializers.CharField(source="program.name", read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = FeePlan
        fields = (
            "id", "branch", "name", "academic_year", "program", "program_name", "term", "head", "head_name",
            "instalments", "total",
        )

    def validate_instalments(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one instalment.")
        seqs = [i["sequence"] for i in value]
        if len(seqs) != len(set(seqs)):
            raise serializers.ValidationError("Instalment numbers must be unique.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        rows = validated_data.pop("instalments")
        plan = FeePlan.objects.create(**validated_data)
        FeePlanInstalment.objects.bulk_create([FeePlanInstalment(plan=plan, **r) for r in rows])
        return plan

    @transaction.atomic
    def update(self, instance, validated_data):
        rows = validated_data.pop("instalments", None)
        instance = super().update(instance, validated_data)
        if rows is not None:
            from apps.fees.models import Charge

            billed = Charge.objects.filter(
                source_type=Charge.Source.PLAN, source_id__in=[f"inst:{i.pk}" for i in instance.instalments.all()],
                cancelled_at__isnull=True,
            ).exists()
            if billed:
                raise serializers.ValidationError(
                    {"instalments": "Students have already been billed from this plan; change their charges instead."}
                )
            instance.instalments.all().delete()
            FeePlanInstalment.objects.bulk_create([FeePlanInstalment(plan=instance, **r) for r in rows])
        return instance


class ChargeSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)
    head_name = serializers.CharField(source="head.name", read_only=True)
    net = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, default=Decimal("0"))
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, default=None)

    class Meta:
        model = Charge
        fields = (
            "id", "branch", "student", "student_name", "admission_no", "head", "head_name", "description",
            "due_date", "amount", "discount", "net", "paid", "outstanding", "source_type", "cancelled_at",
            "created_at",
        )
        read_only_fields = ("discount", "source_type", "cancelled_at", "created_at")


class AdjustmentSerializer(serializers.Serializer):
    student = ScopedPrimaryKeyRelatedField(queryset=Student.objects.all())
    head = ScopedPrimaryKeyRelatedField(queryset=FeeHead.objects.all())
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, help_text="Negative for a credit note")
    description = serializers.CharField(max_length=200)
    due_date = serializers.DateField(required=False)

    def validate_amount(self, value):
        if value == 0:
            raise serializers.ValidationError("Amount cannot be zero.")
        return value


class ConcessionSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)
    head_name = serializers.CharField(source="head.name", read_only=True)

    class Meta:
        model = Concession
        fields = (
            "id", "branch", "student", "student_name", "admission_no", "head", "head_name", "academic_year",
            "kind", "value", "reason", "note", "status", "requested_by", "decided_by", "decided_at", "created_at",
        )
        read_only_fields = ("status", "requested_by", "decided_by", "decided_at", "created_at")

    def validate(self, attrs):
        if attrs.get("kind", Concession.Kind.PERCENT) == Concession.Kind.PERCENT and attrs.get("value", 0) > 100:
            raise serializers.ValidationError({"value": "A percentage cannot exceed 100."})
        return attrs


class ReceiptLineSerializer(serializers.ModelSerializer):
    description = serializers.CharField(source="charge.description", read_only=True)
    head_name = serializers.CharField(source="charge.head.name", read_only=True)

    class Meta:
        model = ReceiptLine
        fields = ("id", "charge", "description", "head_name", "amount")


class ReceiptSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)
    lines = ReceiptLineSerializer(many=True, read_only=True)
    is_cancelled = serializers.SerializerMethodField()

    class Meta:
        model = Receipt
        fields = (
            "id", "branch", "number", "date", "student", "student_name", "admission_no", "mode", "reference",
            "amount", "received_by", "note", "print_count", "is_cancelled", "cancelled_at", "cancelled_by",
            "cancel_reason", "lines", "created_at",
        )
        read_only_fields = fields

    def get_is_cancelled(self, obj) -> bool:
        return obj.cancelled_at is not None


class LineInSerializer(serializers.Serializer):
    charge = ScopedPrimaryKeyRelatedField(queryset=Charge.objects.filter(cancelled_at__isnull=True))
    amount = serializers.DecimalField(**POSITIVE)


class CollectSerializer(serializers.Serializer):
    student = ScopedPrimaryKeyRelatedField(queryset=Student.objects.all())
    mode = serializers.ChoiceField(choices=Receipt.Mode.choices)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    date = serializers.DateField(required=False)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    lines = LineInSerializer(many=True, required=False)
    amount = serializers.DecimalField(**POSITIVE, required=False)

    def validate(self, attrs):
        if bool(attrs.get("lines")) == bool(attrs.get("amount")):
            raise serializers.ValidationError("Send either `lines` or `amount`, not both.")
        return attrs


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class RefundSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = Refund
        fields = ("id", "branch", "student", "student_name", "date", "mode", "reference", "amount", "reason", "created_by")
        read_only_fields = fields


class RefundInSerializer(serializers.Serializer):
    student = ScopedPrimaryKeyRelatedField(queryset=Student.objects.all())
    mode = serializers.ChoiceField(choices=Receipt.Mode.choices)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=200)
    date = serializers.DateField(required=False)
    lines = LineInSerializer(many=True)


class StudentAccountSerializer(BranchScopedSerializer):
    """One row per student: totals for the dues list / defaulters report."""

    total_charged = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    overdue = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    program = serializers.SerializerMethodField()
    section = serializers.SerializerMethodField()
    guardian_name = serializers.SerializerMethodField()
    guardian_phone = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = (
            "id", "branch", "admission_no", "full_name", "program", "section", "guardian_name", "guardian_phone",
            "total_charged", "total_paid", "outstanding", "overdue",
        )

    def _enrollment(self, obj):
        if not hasattr(obj, "_enr"):
            obj._enr = obj.current_enrollment
        return obj._enr

    def _guardian(self, obj):
        return next((g.guardian for g in obj.guardian_links.all() if g.is_primary), None)

    def get_program(self, obj) -> str | None:
        e = self._enrollment(obj)
        return e.program.name if e else None

    def get_section(self, obj) -> str | None:
        e = self._enrollment(obj)
        return e.section.name if e and e.section else None

    def get_guardian_name(self, obj) -> str | None:
        g = self._guardian(obj)
        return g.full_name if g else None

    def get_guardian_phone(self, obj) -> str | None:
        g = self._guardian(obj)
        return g.phone if g else None
