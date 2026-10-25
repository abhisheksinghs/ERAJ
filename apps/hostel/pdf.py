"""Weekly mess menu as a one-page A4 landscape PDF for the notice board."""
from django.template.loader import render_to_string
from django.utils import timezone

from apps.hostel.models import Meal, MenuItem, Mess

MEAL_HI = {"breakfast": "नाश्ता", "lunch": "दोपहर का भोजन", "snacks": "शाम का नाश्ता", "dinner": "रात का भोजन"}
DAY_HI = ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]


def menu_document(mess: Mess, *, lang: str = "en"):
    """The rendered WeasyPrint document (tests check it fits one page)."""
    from weasyprint import HTML

    hi = lang == "hi"
    slots = {(i.day, i.meal): i for i in MenuItem.objects.filter(mess=mess)}
    rows = []
    for day in MenuItem.Day:
        cells = []
        for meal in Meal:
            item = slots.get((day.value, meal.value))
            cells.append({
                "text": (item.items_hi or item.items) if (item and hi) else (item.items if item else ""),
                "veg": item.is_veg if item else True,
            })
        rows.append({"day": DAY_HI[day.value] if hi else day.label, "cells": cells})
    html = render_to_string("hostel/menu.html", {
        "mess": mess, "branch": mess.branch, "rows": rows, "hi": hi,
        "meals": [MEAL_HI[m.value] if hi else m.label for m in Meal],
        "printed_at": timezone.localtime(),
    })
    return HTML(string=html).render()


def menu_pdf(mess: Mess, *, lang: str = "en") -> bytes:
    return menu_document(mess, lang=lang).write_pdf()
