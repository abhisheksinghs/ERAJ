from rest_framework import serializers

from apps.fees.models import FeeStructure, Payment


class FeeStructureSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeStructure
        fields = ("id", "name", "term", "amount", "due_date", "created_at")
        read_only_fields = ("created_at",)


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ("id", "fee_structure", "payer_name", "payer_reference", "amount", "receipt_no", "created_at")
        read_only_fields = ("receipt_no", "created_at")


class RecordPaymentSerializer(serializers.Serializer):
    fee_structure = serializers.PrimaryKeyRelatedField(queryset=FeeStructure.objects.all())
    payer_name = serializers.CharField(max_length=255)
    payer_reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)


class CollectionsSerializer(serializers.Serializer):
    fee_structure = serializers.IntegerField()
    total_collected = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_count = serializers.IntegerField()
