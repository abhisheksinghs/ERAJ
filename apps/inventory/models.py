"""Inventory module. TENANT_APPS. Structurally a copy-adapt of
apps.library's Book/Issue (same available-vs-total pattern) minus due
dates/fines/holds — stock issue/return has no lending-period concept."""
from django.db import models
from django.db.models import F, Q

from apps.core.mixins import SoftDelete, TimeStamped


class Item(TimeStamped, SoftDelete):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=100, blank=True)
    quantity_total = models.PositiveIntegerField(default=1)
    quantity_available = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.CheckConstraint(check=Q(quantity_available__gte=0), name="inventory_item_available_nonneg"),
            models.CheckConstraint(
                check=Q(quantity_available__lte=F("quantity_total")), name="inventory_item_available_lte_total"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"


class IssueRecord(TimeStamped):
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="issues")
    issued_to = models.CharField(max_length=255)
    returned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.item} -> {self.issued_to}"
