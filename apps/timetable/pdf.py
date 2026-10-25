"""Printable timetables (section / teacher / room) and the substitution register."""
from django.template.loader import render_to_string
from django.utils import timezone


def _rows(grid: dict) -> list[dict]:
    """Normalise section grids (slots) and teacher/room grids (time bands) to rows × days."""
    cells = {}
    if grid["kind"] == "section":
        for c in grid["cells"]:
            cells[(c["slot"], c["day"])] = c
        return [{"label": s["label"], "start": s["start"], "end": s["end"], "is_break": s["is_break"],
                 "cells": [cells.get((s["slot"], d["day"])) if d["day"] in s["days"] else {"off": True} for d in grid["days"]]}
                for s in grid["slots"]]
    for c in grid["cells"]:
        cells[(c["band"], c["day"])] = c
    return [{"label": b["label"], "start": b["start"], "end": b["end"], "is_break": False,
             "cells": [cells.get((b["band"], d["day"])) for d in grid["days"]]} for b in grid["bands"]]


def grid_document(grid: dict, *, branch):
    from weasyprint import HTML

    html = render_to_string("timetable/grid.html", {"g": grid, "rows": _rows(grid), "branch": branch, "printed_at": timezone.localtime()})
    return HTML(string=html).render()


def grid_pdf(grid: dict, *, branch) -> bytes:
    return grid_document(grid, branch=branch).write_pdf()


def register_pdf(data: dict, *, branch) -> bytes:
    from weasyprint import HTML

    html = render_to_string("timetable/register.html", {"d": data, "branch": branch, "printed_at": timezone.localtime()})
    return HTML(string=html).write_pdf()
