"""Report cards (per exam and annual, whole class in one PDF) and date sheets."""
from django.template.loader import render_to_string
from django.utils import timezone

from apps.exam.models import Exam


def _logo(branch) -> str | None:
    try:
        return branch.logo.path and f"file://{branch.logo.path}"
    except (ValueError, AttributeError):  # no file
        return None


def _render(template: str, ctx: dict):
    from weasyprint import HTML

    return HTML(string=render_to_string(template, {**ctx, "printed_at": timezone.localtime()})).render()


def report_cards_document(*, exam: Exam, result: dict, rows: list[dict]):
    return _render("exam/report_card.html", {"exam": exam, "branch": exam.branch, "logo": _logo(exam.branch),
                                             "subjects": result["subjects"], "rows": rows, "credit": result["scale_kind"] == "credit",
                                             "bands": exam.scale.bands.all()})


def report_cards_pdf(**kw) -> bytes:
    return report_cards_document(**kw).write_pdf()


def annual_cards_document(*, exams: list[Exam], result: dict, rows: list[dict]):
    branch = exams[0].branch
    return _render("exam/annual_card.html", {"exams": result["exams"], "first": exams[0], "branch": branch, "logo": _logo(branch),
                                             "rows": rows, "bands": exams[-1].scale.bands.all()})


def annual_cards_pdf(**kw) -> bytes:
    return annual_cards_document(**kw).write_pdf()


def date_sheet_pdf(exam: Exam) -> bytes:
    return _render("exam/date_sheet.html", {"exam": exam, "branch": exam.branch, "logo": _logo(exam.branch),
                                            "subjects": exam.subjects.select_related("subject").order_by("date", "start_time", "sequence")}).write_pdf()
