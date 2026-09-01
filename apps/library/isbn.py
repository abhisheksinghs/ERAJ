"""ISBN metadata lookup for prefilling a Book form.

ponytail: OpenLibrary only, 5s timeout, best-effort. Add a fallback provider
(Google Books) if coverage complains. Outbound HTTP in the request path is
acceptable here — low frequency, explicit staff action, hard timeout.
"""
import json
import re
import urllib.request
from urllib.error import URLError

from apps.core.exceptions import UpstreamError

_URL = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"


def lookup(isbn: str) -> dict:
    try:
        with urllib.request.urlopen(_URL.format(isbn=isbn), timeout=5) as resp:  # noqa: S310 - fixed https host
            data = json.load(resp)
    except (URLError, TimeoutError, ValueError) as exc:
        raise UpstreamError(f"ISBN lookup failed: {exc}") from exc

    rec = data.get(f"ISBN:{isbn}")
    if not rec:
        raise UpstreamError("No metadata found for that ISBN.")

    return {
        "isbn": isbn,
        "title": rec.get("title", ""),
        "author": ", ".join(a.get("name", "") for a in rec.get("authors", [])),
        "publisher": ", ".join(p.get("name", "") for p in rec.get("publishers", [])),
        "published_year": _year(rec.get("publish_date", "")),
    }


def _year(text: str):
    m = re.search(r"\d{4}", text)
    return int(m.group()) if m else None
