import uuid

from django.db import transaction

from apps.core.audit import record
from apps.fees.models import FeeStructure, Payment


@transaction.atomic
def record_payment(*, fee_structure: FeeStructure, payer_name: str, amount, payer_reference: str = "") -> Payment:
    payment = Payment.objects.create(
        fee_structure=fee_structure,
        payer_name=payer_name,
        payer_reference=payer_reference,
        amount=amount,
        receipt_no=f"RCPT-{uuid.uuid4().hex[:10].upper()}",
    )
    record(
        "fees.payment_recorded",
        detail={"payment": payment.pk, "fee_structure": fee_structure.pk, "amount": str(amount)},
    )
    return payment
