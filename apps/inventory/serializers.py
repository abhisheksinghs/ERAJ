from rest_framework import serializers

from apps.inventory.models import Item, IssueRecord
from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField


class ItemSerializer(BranchScopedSerializer):
    class Meta:
        model = Item
        fields = ("id", "branch", "name", "sku", "category", "quantity_total", "quantity_available", "created_at")
        read_only_fields = ("quantity_available", "created_at")

    def create(self, validated_data):
        validated_data["quantity_available"] = validated_data.get("quantity_total", 1)
        return super().create(validated_data)


class IssueRecordSerializer(BranchScopedSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = IssueRecord
        fields = ("id", "branch", "item", "item_name", "issued_to", "returned_at", "created_at")
        read_only_fields = ("returned_at", "created_at")


class IssueCreateSerializer(serializers.Serializer):
    item = ScopedPrimaryKeyRelatedField(queryset=Item.objects.all())
    issued_to = serializers.CharField(max_length=255)
