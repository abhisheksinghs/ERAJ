from decimal import Decimal

from rest_framework import serializers

from apps.inventory.models import (
    DirectPurchase, DirectPurchaseLine, GoodsReceipt, InventorySettings, IssueRecord, Item, POLine, PurchaseOrder,
    Requisition, RequisitionLine, StockMove, Store, Vendor,
)
from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.people.models import Department, Staff

POSITIVE = Decimal("0.001")


class StoreSerializer(BranchScopedSerializer):
    mess_name = serializers.CharField(source="mess.name", read_only=True, default=None)

    class Meta:
        model = Store
        fields = ("id", "branch", "name", "kind", "mess", "mess_name")


class VendorSerializer(BranchScopedSerializer):
    class Meta:
        model = Vendor
        fields = ("id", "branch", "name", "contact_person", "phone", "email", "gstin", "address")

    def to_internal_value(self, data):
        if hasattr(data, "copy") and isinstance(data.get("gstin"), str):
            data = data.copy()
            data["gstin"] = data["gstin"].strip().upper()
        return super().to_internal_value(data)


class ItemSerializer(BranchScopedSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)
    value = serializers.SerializerMethodField()
    low = serializers.SerializerMethodField()
    opening_quantity = serializers.DecimalField(max_digits=12, decimal_places=3, write_only=True, required=False, min_value=Decimal("0"))
    opening_rate = serializers.DecimalField(max_digits=12, decimal_places=2, write_only=True, required=False, min_value=Decimal("0"))

    class Meta:
        model = Item
        fields = ("id", "branch", "store", "store_name", "code", "name", "name_hi", "category", "unit", "kind", "location",
                  "reorder_level", "quantity", "avg_cost", "value", "low", "opening_quantity", "opening_rate")
        read_only_fields = ("quantity", "avg_cost")

    def get_value(self, obj) -> str:
        return str((obj.quantity * obj.avg_cost).quantize(Decimal("0.01")))

    def get_low(self, obj) -> bool:
        return bool(obj.reorder_level) and obj.quantity <= obj.reorder_level

    def validate_code(self, v):
        return v.strip().upper()


class StockMoveSerializer(BranchScopedSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    staff_name = serializers.CharField(source="staff.full_name", read_only=True, default=None)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default=None)

    class Meta:
        model = StockMove
        fields = ("id", "branch", "item", "item_name", "at", "kind", "quantity", "rate", "value", "balance", "staff",
                  "staff_name", "department", "department_name", "vendor_name", "reference", "note", "by")
        read_only_fields = fields


class StockIssueSerializer(serializers.Serializer):
    item = ScopedPrimaryKeyRelatedField(queryset=Item.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=POSITIVE)
    staff = ScopedPrimaryKeyRelatedField(queryset=Staff.objects.all(), required=False, allow_null=True)
    department = ScopedPrimaryKeyRelatedField(queryset=Department.objects.all(), required=False, allow_null=True)
    due_back = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class IssueRecordSerializer(BranchScopedSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)

    class Meta:
        model = IssueRecord
        fields = ("id", "branch", "item", "item_name", "staff", "staff_name", "department", "quantity", "issued_on",
                  "due_back", "status", "closed_on", "note")
        read_only_fields = fields


class CloseIssueSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["returned", "damaged", "lost"])
    note = serializers.CharField(required=False, allow_blank=True, default="")


class AdjustSerializer(serializers.Serializer):
    counted = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0"))
    reason = serializers.CharField()


class RequisitionLineSerializer(serializers.ModelSerializer):
    serializer_related_field = ScopedPrimaryKeyRelatedField
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = RequisitionLine
        fields = ("item", "item_name", "quantity", "estimated_rate")
        extra_kwargs = {"quantity": {"min_value": POSITIVE}, "estimated_rate": {"min_value": Decimal("0")}}


class RequisitionSerializer(BranchScopedSerializer):
    lines = RequisitionLineSerializer(many=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    approved_by = serializers.SerializerMethodField()

    class Meta:
        model = Requisition
        fields = ("id", "branch", "department", "department_name", "purpose", "status", "total", "approvals_needed",
                  "approved_by", "requested_by", "decided_note", "lines", "created_at")
        read_only_fields = ("status", "total", "approvals_needed", "requested_by", "decided_note", "created_at")

    def get_approved_by(self, obj) -> list[str]:
        return [a.by for a in obj.approvals.all()]


class POLineSerializer(serializers.ModelSerializer):
    serializer_related_field = ScopedPrimaryKeyRelatedField
    item_name = serializers.CharField(source="item.name", read_only=True)
    unit = serializers.CharField(source="item.unit", read_only=True)
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)

    class Meta:
        model = POLine
        fields = ("id", "item", "item_name", "unit", "quantity", "rate", "received", "outstanding")
        read_only_fields = ("id", "received")
        extra_kwargs = {"quantity": {"min_value": POSITIVE}, "rate": {"min_value": Decimal("0")}}


class PurchaseOrderSerializer(BranchScopedSerializer):
    lines = POLineSerializer(many=True, required=False)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    received_percent = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = ("id", "branch", "number", "requisition", "vendor", "vendor_name", "order_date", "status", "total",
                  "received_percent", "terms", "created_by", "lines")
        read_only_fields = ("number", "order_date", "status", "total", "created_by")

    def get_received_percent(self, obj) -> int:
        lines = list(obj.lines.all())
        ordered = sum((ln.quantity * ln.rate for ln in lines), Decimal("0"))
        got = sum((ln.received * ln.rate for ln in lines), Decimal("0"))
        return int(round(100 * got / ordered)) if ordered else 0


class ReceiveSerializer(serializers.Serializer):
    lines = serializers.DictField(child=serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0")))
    challan_no = serializers.CharField(required=False, allow_blank=True, default="")


class GoodsReceiptSerializer(BranchScopedSerializer):
    order_number = serializers.CharField(source="order.number", read_only=True)
    lines = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceipt
        fields = ("id", "branch", "order", "order_number", "received_on", "challan_no", "received_by", "lines")
        read_only_fields = fields

    def get_lines(self, obj) -> list[dict]:
        return [{"item": ln.po_line.item.name, "quantity": str(ln.quantity)} for ln in obj.lines.select_related("po_line__item")]


class DirectPurchaseLineSerializer(serializers.ModelSerializer):
    serializer_related_field = ScopedPrimaryKeyRelatedField
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = DirectPurchaseLine
        fields = ("item", "item_name", "quantity", "rate")
        extra_kwargs = {"quantity": {"min_value": POSITIVE}, "rate": {"min_value": Decimal("0")}}


class DirectPurchaseSerializer(BranchScopedSerializer):
    lines = DirectPurchaseLineSerializer(many=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)

    class Meta:
        model = DirectPurchase
        fields = ("id", "branch", "vendor", "vendor_name", "bill_no", "bill_date", "total", "note", "created_by", "lines")
        read_only_fields = ("total", "created_by")


class InventorySettingsSerializer(BranchScopedSerializer):
    class Meta:
        model = InventorySettings
        fields = ("id", "branch", "approval_levels")

    def validate_approval_levels(self, v):
        if not isinstance(v, list) or not v:
            raise serializers.ValidationError("At least one level.")
        prev = Decimal("-1")
        for i, lvl in enumerate(v):
            try:
                n = int(lvl["approvals"])
                top = lvl.get("up_to")
                top = None if top in (None, "") else Decimal(str(top))
            except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                raise serializers.ValidationError(f"Level {i + 1}: up_to (₹ or empty) and approvals.") from exc
            if n < 1 or n > 5:
                raise serializers.ValidationError(f"Level {i + 1}: 1 to 5 approvals.")
            if top is None and i != len(v) - 1:
                raise serializers.ValidationError("Only the last level can be open-ended.")
            if top is not None and top <= prev:
                raise serializers.ValidationError("Levels must rise.")
            prev = top if top is not None else prev
        return v


class StockReasonSerializer(serializers.Serializer):
    reason = serializers.CharField()


class StockNoteSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")
