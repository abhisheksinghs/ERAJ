from decimal import Decimal

from rest_framework import serializers

from apps.fees.models import FeeStructure, Payment
from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField


class FeeStructureSerializer(BranchScopedSerializer):
    class Meta:
        model = FeeStructure
        fields = ("id", "branch", "name", "term", "amount", "due_date", "created_at")
        read_only_fields = ("created_at",)


class PaymentSerializer(BranchScopedSerializer):
    class Meta:
        model = Payment
        fields = ("id", "branch", "fee_structure", "payer_name", "payer_reference", "amount", "receipt_no", "created_at")
        read_only_fields = ("receipt_no", "created_at")


class RecordPaymentSerializer(serializers.Serializer):
    fee_structure = ScopedPrimaryKeyRelatedField(queryset=FeeStructure.objects.all())
    payer_name = serializers.CharField(max_length=255)
    payer_reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))


class CollectionsSerializer(serializers.Serializer):
    fee_structure = serializers.IntegerField()
    total_collected = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_count = serializers.IntegerField()
