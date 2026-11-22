"""Purchase order PDF for the vendor."""
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.numwords import rupees_in_words


def po_pdf(po) -> bytes:
    from weasyprint import HTML

    lines = [{"n": i, "item": ln.item, "quantity": ln.quantity, "rate": ln.rate, "amount": ln.quantity * ln.rate}
             for i, ln in enumerate(po.lines.select_related("item"), start=1)]
    html = render_to_string("inventory/po.html", {"po": po, "branch": po.branch, "lines": lines,
                                                  "words": rupees_in_words(po.total), "printed_at": timezone.localtime()})
    return HTML(string=html).write_pdf()
