"""Monthly attendance register as an A4 landscape PDF (dates across, students down)."""
from django.template.loader import render_to_string
from django.utils import timezone


def register_document(data: dict, *, branch):
    from weasyprint import HTML

    html = render_to_string("attendance/register.html", {"d": data, "branch": branch, "printed_at": timezone.localtime()})
    return HTML(string=html).render()


def register_pdf(data: dict, *, branch) -> bytes:
    return register_document(data, branch=branch).write_pdf()
