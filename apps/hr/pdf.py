"""Printable monthly staff attendance register."""
from django.template.loader import render_to_string
from django.utils import timezone


def register_pdf(data: dict, *, branch) -> bytes:
    from weasyprint import HTML

    html = render_to_string("hr/register.html", {"d": data, "branch": branch, "printed_at": timezone.localtime()})
    return HTML(string=html).write_pdf()
