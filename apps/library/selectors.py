from django.db.models import DecimalField, OuterRef, Subquery


def fines_with_fee_balance(qs):
    """Fines annotated with `fee_outstanding`: what is still unpaid on the fee
    account for fines billed to Fees (None for fines kept at the library desk,
    or once the fee charge is cancelled)."""
    from apps.fees.models import Charge
    from apps.fees.selectors import charges_with_balance

    owed = charges_with_balance(Charge.objects.filter(pk=OuterRef("charge_id"))).values("outstanding")[:1]
    return qs.annotate(fee_outstanding=Subquery(owed, output_field=DecimalField(max_digits=12, decimal_places=2)))
