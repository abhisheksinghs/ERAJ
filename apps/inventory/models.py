"""
Inventory (ADR-010). Branch-owned (ADR-001). `StockMove` is the ledger — every
quantity change goes through `apps.inventory.services` under a row lock on the
item; `Item.quantity` and `Item.avg_cost` are its running totals.
"""
from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from apps.core.mixins import SoftDelete, TimeStamped
from apps.org.models import BranchOwned

MONEY = {"max_digits": 12, "decimal_places": 2}
QTY = {"max_digits": 12, "decimal_places": 3}
GSTIN = RegexValidator(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$", "GSTIN must look like 10ABCDE1234F1Z5.")


class InventorySettings(TimeStamped, BranchOwned):
    """approval_levels: [{"up_to": 50000, "approvals": 1}, {"up_to": null, "approvals": 2}] (sample)."""

    approval_levels = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name_plural = "inventory settings"
        constraints = [models.UniqueConstraint(fields=["branch"], name="inventory_one_settings_per_branch")]


class Store(TimeStamped, SoftDelete, BranchOwned):
    class Kind(models.TextChoices):
        GENERAL = "general", "General store"
        MESS = "mess", "Mess store (provisions)"

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.GENERAL)
    mess = models.ForeignKey("hostel.Mess", null=True, blank=True, on_delete=models.SET_NULL, related_name="stores")

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=["branch", "name"], name="inventory_store_unique")]

    def __str__(self) -> str:
        return self.name


class Vendor(TimeStamped, SoftDelete, BranchOwned):
    name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    gstin = models.CharField("GSTIN", max_length=15, blank=True, validators=[GSTIN])
    address = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Item(TimeStamped, SoftDelete, BranchOwned):
    class Kind(models.TextChoices):
        CONSUMABLE = "consumable", "Consumable"
        RETURNABLE = "returnable", "Returnable asset"

    class Unit(models.TextChoices):
        PIECE = "piece", "Piece"
        BOX = "box", "Box"
        REAM = "ream", "Ream"
        PACKET = "packet", "Packet"
        KG = "kg", "Kg"
        LITRE = "litre", "Litre"
        SET = "set", "Set"
        OTHER = "other", "Other"

    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="items")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    name_hi = models.CharField(max_length=150, blank=True)
    category = models.CharField(max_length=80, blank=True)
    unit = models.CharField(max_length=8, choices=Unit.choices, default=Unit.PIECE)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CONSUMABLE)
    location = models.CharField(max_length=100, blank=True, help_text="Room / rack")
    reorder_level = models.DecimalField(**QTY, default=0)
    quantity = models.DecimalField(**QTY, default=0)
    avg_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0, help_text="Weighted average cost per unit")

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=["branch", "code"], name="inventory_item_code_unique"),
            models.CheckConstraint(check=Q(quantity__gte=0), name="inventory_item_qty_nonneg"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class StockMove(BranchOwned):
    class Kind(models.TextChoices):
        RECEIPT = "receipt", "Goods received (order)"
        PURCHASE = "purchase", "Direct purchase"
        ISSUE = "issue", "Issued"
        RETURN = "return", "Returned"
        DAMAGED = "damaged", "Returned damaged (written off)"
        LOST = "lost", "Lost (written off)"
        ADJUST = "adjust", "Stock adjustment"
        OPENING = "opening", "Opening stock"

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="moves")
    at = models.DateTimeField()
    kind = models.CharField(max_length=8, choices=Kind.choices)
    quantity = models.DecimalField(**QTY, help_text="+ in, − out")
    rate = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    value = models.DecimalField(**MONEY, default=0)
    balance = models.DecimalField(**QTY, help_text="Item quantity after this move")
    department = models.ForeignKey("people.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    staff = models.ForeignKey("people.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="stock_moves")
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL, related_name="moves")
    reference = models.CharField(max_length=80, blank=True)
    note = models.CharField(max_length=255, blank=True)
    by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("item", "at", "pk")
        indexes = [models.Index(fields=["branch", "kind", "at"], name="inventory_move_branch_kind_at")]


class IssueRecord(TimeStamped, BranchOwned):
    """A returnable asset with a staff member until it comes back."""

    class Status(models.TextChoices):
        OUT = "out", "With staff"
        RETURNED = "returned", "Returned"
        DAMAGED = "damaged", "Returned damaged"
        LOST = "lost", "Lost"

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="issues")
    staff = models.ForeignKey("people.Staff", on_delete=models.PROTECT, related_name="items_held")
    department = models.ForeignKey("people.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    quantity = models.DecimalField(**QTY, default=1)
    issued_on = models.DateField()
    due_back = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OUT)
    closed_on = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-issued_on", "-pk")


class Requisition(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Awaiting approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        ORDERED = "ordered", "Ordered"

    department = models.ForeignKey("people.Department", on_delete=models.PROTECT, related_name="requisitions")
    purpose = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    total = models.DecimalField(**MONEY, default=0)
    approvals_needed = models.PositiveSmallIntegerField(default=1)
    requested_by = models.CharField(max_length=255, blank=True)
    decided_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at",)


class RequisitionLine(models.Model):
    requisition = models.ForeignKey(Requisition, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(**QTY)
    estimated_rate = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [models.CheckConstraint(check=Q(quantity__gt=0), name="inventory_req_line_qty_pos")]


class RequisitionApproval(models.Model):
    requisition = models.ForeignKey(Requisition, on_delete=models.CASCADE, related_name="approvals")
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    by = models.CharField(max_length=255)
    at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["requisition", "user"], name="inventory_one_approval_per_user")]


class POCounter(models.Model):
    branch = models.ForeignKey("org.Branch", on_delete=models.CASCADE, related_name="+")
    financial_year = models.CharField(max_length=7)
    last = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["branch", "financial_year"], name="inventory_po_counter_unique")]


class PurchaseOrder(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PARTLY = "partly", "Partly received"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=30)
    requisition = models.ForeignKey(Requisition, null=True, blank=True, on_delete=models.PROTECT, related_name="orders")
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="orders")
    order_date = models.DateField()
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.OPEN)
    total = models.DecimalField(**MONEY, default=0)
    terms = models.TextField(blank=True)
    created_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-order_date", "-pk")
        constraints = [models.UniqueConstraint(fields=["branch", "number"], name="inventory_po_number_unique")]

    def __str__(self) -> str:
        return self.number


class POLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(**QTY)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    received = models.DecimalField(**QTY, default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(check=Q(quantity__gt=0), name="inventory_po_line_qty_pos"),
            models.CheckConstraint(check=Q(received__lte=models.F("quantity")), name="inventory_po_line_not_over"),
        ]

    @property
    def outstanding(self):
        return self.quantity - self.received


class GoodsReceipt(TimeStamped, BranchOwned):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    received_on = models.DateField()
    challan_no = models.CharField(max_length=60, blank=True, help_text="Delivery challan / bill number")
    received_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-received_on", "-pk")


class GoodsReceiptLine(models.Model):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    po_line = models.ForeignKey(POLine, on_delete=models.PROTECT, related_name="receipt_lines")
    quantity = models.DecimalField(**QTY)


class DirectPurchase(TimeStamped, BranchOwned):
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="direct_purchases")
    bill_no = models.CharField(max_length=60)
    bill_date = models.DateField()
    total = models.DecimalField(**MONEY, default=0)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-bill_date", "-pk")
        constraints = [models.UniqueConstraint(fields=["vendor", "bill_no"], name="inventory_bill_once_per_vendor")]


class DirectPurchaseLine(models.Model):
    purchase = models.ForeignKey(DirectPurchase, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(**QTY)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
