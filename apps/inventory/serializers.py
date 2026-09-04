from rest_framework import serializers

from apps.inventory.models import Item, IssueRecord


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ("id", "name", "sku", "category", "quantity_total", "quantity_available", "created_at")
        read_only_fields = ("quantity_available", "created_at")

    def create(self, validated_data):
        validated_data["quantity_available"] = validated_data.get("quantity_total", 1)
        return super().create(validated_data)


class IssueRecordSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = IssueRecord
        fields = ("id", "item", "item_name", "issued_to", "returned_at", "created_at")
        read_only_fields = ("returned_at", "created_at")


class IssueCreateSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    issued_to = serializers.CharField(max_length=255)
