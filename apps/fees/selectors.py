"""
Read-side ledger queries, computed in SQL so lists of thousands of students
stay one query each.

    received(charge)    = Σ receipt lines on live receipts
    paid(charge)        = received − Σ refund lines        (net cash kept)
    outstanding(charge) = amount − discount − received

A refund returns money that was not owed (paid twice, withdrawal, a concession
granted after payment), so it lowers `paid` but does NOT reopen the due. A
payment that failed (bounced cheque) is a receipt *cancellation*, which does
reopen it because cancelled receipts stop counting as received.
"""
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.fees.models import Charge, ReceiptLine, RefundLine

ZERO = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))
MONEY = DecimalField(max_digits=12, decimal_places=2)


def charges_with_balance(qs=None):
    """Charges annotated with `paid` and `outstanding`; cancelled charges excluded."""
    qs = (qs if qs is not None else Charge.objects.all()).filter(cancelled_at__isnull=True)
    received = Coalesce(
        Subquery(
            ReceiptLine.objects.filter(charge=OuterRef("pk"), receipt__cancelled_at__isnull=True)
            .values("charge").annotate(t=Sum("amount")).values("t")[:1],
            output_field=MONEY,
        ),
        ZERO,
    )
    refunded = Coalesce(
        Subquery(
            RefundLine.objects.filter(charge=OuterRef("pk")).values("charge").annotate(t=Sum("amount")).values("t")[:1],
            output_field=MONEY,
        ),
        ZERO,
    )
    return (
        qs.annotate(received=received)
        .annotate(paid=ExpressionWrapper(F("received") - refunded, output_field=MONEY))
        .annotate(outstanding=ExpressionWrapper(F("amount") - F("discount") - F("received"), output_field=MONEY))
    )


def _student_sum(charge_filter: Q, value):
    return Coalesce(
        Subquery(
            charges_with_balance(Charge.objects.filter(charge_filter, student=OuterRef("pk")))
            .values("student").annotate(t=Sum(value)).values("t")[:1],
            output_field=MONEY,
        ),
        ZERO,
    )


def students_with_dues(student_qs, today):
    """Students annotated with total charged (net of concessions), paid,
    outstanding and overdue (outstanding on charges already past due)."""
    return student_qs.annotate(
        total_charged=_student_sum(Q(), F("amount") - F("discount")),
        total_paid=_student_sum(Q(), F("paid")),
        outstanding=_student_sum(Q(), F("outstanding")),
        overdue=_student_sum(Q(due_date__lt=today), F("outstanding")),
    )
