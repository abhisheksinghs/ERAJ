"""Fee receipt as PDF (WeasyPrint). Reprints are marked DUPLICATE and cancelled
receipts CANCELLED, as the scope requires. Hindi names render with the Noto
Devanagari font installed in the image."""
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.numwords import rupees_in_words
from apps.fees.models import Receipt


def receipt_pdf(receipt: Receipt, *, duplicate: bool) -> bytes:
    from weasyprint import HTML  # heavy import; only when a PDF is asked for

    enrollment = receipt.student.current_enrollment
    lines = receipt.lines.select_related("charge", "charge__head").order_by("charge__due_date", "charge_id")
    html = render_to_string(
        "fees/receipt.html",
        {
            "r": receipt,
            "branch": receipt.branch,
            "student": receipt.student,
            "enrollment": enrollment,
            "lines": lines,
            "words": rupees_in_words(receipt.amount),
            "duplicate": duplicate,
            "printed_at": timezone.localtime(),
        },
    )
    return HTML(string=html).write_pdf()
