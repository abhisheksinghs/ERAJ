"""
Fees module. TENANT_APPS. Deliberately no per-student invoice/ledger — that
needs a real enrollment model this build doesn't have yet (see
docs/REQUIREMENTS_GAP_ANALYSIS.md). What's here: fee structures and the
payments recorded against them, with a receipt number and a collections
report. "Dues" (who still owes what) needs invoicing and is out of scope.
"""
from django.db import models

from apps.core.mixins import TimeStamped


class FeeStructure(TimeStamped):
    name = models.CharField(max_length=255)
    term = models.CharField(max_length=100, blank=True, help_text='e.g. "2026 Annual"')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.name} ({self.amount})"


class Payment(TimeStamped):
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.PROTECT, related_name="payments")
    payer_name = models.CharField(max_length=255)
    payer_reference = models.CharField(max_length=100, blank=True, help_text="admission/roll no, etc.")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    receipt_no = models.CharField(max_length=30, unique=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.receipt_no} — {self.payer_name} ({self.amount})"
