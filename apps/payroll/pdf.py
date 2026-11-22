"""Payslips as PDF (WeasyPrint), one page per staff member, amount in words."""
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.numwords import rupees_in_words


def payslips_pdf(slips, *, branch) -> bytes:
    from weasyprint import HTML

    pages = []
    for s in slips:
        lines = list(s.lines.all())
        pages.append({
            "s": s, "profile": getattr(s.staff, "hr_profile", None),
            "earnings": [ln for ln in lines if ln.kind == "earning"],
            "deductions": [ln for ln in lines if ln.kind == "deduction"],
            "employer": [ln for ln in lines if ln.kind == "employer"],
            "words": rupees_in_words(s.net_pay),
        })
    html = render_to_string("payroll/payslip.html", {"pages": pages, "branch": branch, "printed_at": timezone.localtime()})
    return HTML(string=html).write_pdf()
