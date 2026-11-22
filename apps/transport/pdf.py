"""Printable rider list (route-wise, grouped by stop) for the driver."""
from itertools import groupby

from django.template.loader import render_to_string
from django.utils import timezone


def riders_pdf(rows, *, branch, route, on) -> bytes:
    from weasyprint import HTML

    groups = []
    for (code, name), items in groupby(rows, key=lambda r: (r["route"], r["route_name"])):
        items = list(items)
        stops = [{"no": no, "name": nm, "pickup": items_[0]["pickup"], "drop": items_[0]["drop"], "riders": items_}
                 for (no, nm), items_ in ((k, list(g)) for k, g in groupby(items, key=lambda r: (r["stop_no"], r["stop"])))]
        groups.append({"code": code, "name": name, "vehicles": sorted({r["vehicle"] for r in items}), "stops": stops,
                       "count": len(items)})
    html = render_to_string("transport/riders.html", {"groups": groups, "branch": branch, "on": on,
                                                      "printed_at": timezone.localtime()})
    return HTML(string=html).write_pdf()
