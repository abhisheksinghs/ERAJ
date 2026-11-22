"""Alert events (ADR-011): who receives them, default channels, default en/hi wording.

Each institution switches events on/off and edits wording (AlertRule / Template); these are the
defaults used until it does. Placeholders come from the caller's context; `{message}` carries the
free text the older call sites pass (core.notify.guardian / staff_role).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Event:
    key: str
    label: str
    label_hi: str
    audience: str  # "guardian" | "staff" | "direct"
    channels: tuple[str, ...]
    en: str
    hi: str
    enabled: bool = True
    bypass_quiet: bool = False
    extra: dict = field(default_factory=dict)


G, S = "guardian", "staff"
SW = ("sms", "whatsapp")

EVENTS: dict[str, Event] = {e.key: e for e in [
    Event("attendance.absent", "Absent today", "आज अनुपस्थित", G, SW,
          "{student} was marked absent today ({date}). — {school}",
          "{student} आज ({date}) अनुपस्थित दर्ज किए गए। — {school}"),
    Event("fees.due_soon", "Fee due soon", "शुल्क देय तिथि निकट", G, SW,
          "Fee of Rs {amount} for {student} is due on {due_date}. — {school}",
          "{student} का Rs {amount} शुल्क {due_date} तक देय है। — {school}"),
    Event("fees.overdue", "Fee overdue", "शुल्क बकाया", G, SW,
          "Fee of Rs {amount} for {student} was due on {due_date} and is unpaid. — {school}",
          "{student} का Rs {amount} शुल्क {due_date} से बकाया है। — {school}"),
    Event("fees.payment_received", "Payment received", "भुगतान प्राप्त", G, ("whatsapp",),
          "Received Rs {amount} for {student}. Receipt {receipt}. Thank you. — {school}",
          "{student} हेतु Rs {amount} प्राप्त हुए। रसीद {receipt}। धन्यवाद। — {school}"),
    Event("exam.results_published", "Results published", "परिणाम प्रकाशित", G, SW,
          "Results of {exam} for {student} are published. See the parent portal. — {school}",
          "{student} के {exam} के परिणाम प्रकाशित। अभिभावक पोर्टल देखें। — {school}"),
    Event("learning.homework_set", "Homework set", "गृहकार्य दिया गया", G, ("whatsapp",),
          "Homework for {student}: {subject} — {title}, due {due_date}. — {school}",
          "{student} का गृहकार्य: {subject} — {title}, जमा तिथि {due_date}। — {school}"),
    Event("library.overdue", "Library book overdue", "पुस्तकालय पुस्तक विलंबित", G, ("whatsapp",),
          "{student} has not returned \"{book}\" (due {due_date}). — {school}",
          "{student} ने \"{book}\" ({due_date} तक) वापस नहीं की। — {school}"),
    Event("outpass.requested", "Outpass requested", "आउटपास अनुरोध", G, ("whatsapp",), "{message}", "{message}", enabled=False),
    Event("outpass.approved", "Outpass approved", "आउटपास स्वीकृत", G, SW, "{message}", "{message}"),
    Event("outpass.rejected", "Outpass rejected", "आउटपास अस्वीकृत", G, SW, "{message}", "{message}"),
    Event("outpass.out", "Hostel check-out", "छात्रावास से प्रस्थान", G, SW, "{message}", "{message}"),
    Event("outpass.returned", "Hostel check-in", "छात्रावास वापसी", G, SW, "{message}", "{message}"),
    Event("outpass.late", "Late return to hostel", "छात्रावास में विलंब से वापसी", G, SW, "{message}", "{message}"),
    Event("outpass.cancelled", "Outpass cancelled", "आउटपास रद्द", G, ("whatsapp",), "{message}", "{message}", enabled=False),
    Event("transport.near_stop", "Bus near the stop", "बस पड़ाव के निकट", G, ("whatsapp",), "{message}", "{message}"),
    Event("notice", "Notice", "सूचना", G, ("whatsapp",), "{title}: {body} — {school}", "{title}: {body} — {school}"),
    Event("transport.over_speed", "Over-speed (staff)", "तेज़ गति (कर्मचारी)", S, ("whatsapp", "email"), "{message}", "{message}"),
    Event("transport.document_expiring", "Vehicle papers expiring (staff)", "वाहन कागज़ात (कर्मचारी)", S, ("email",), "{message}", "{message}"),
    Event("inventory.low_stock", "Low stock (staff)", "कम स्टॉक (कर्मचारी)", S, ("email",), "{message}", "{message}"),
    Event("portal.otp", "Portal login code", "पोर्टल लॉगिन कोड", "direct", ("sms", "whatsapp"),
          "{code} is your {school} portal login code. It expires in 5 minutes. Do not share it.",
          "{code} आपका {school} पोर्टल लॉगिन कोड है। 5 मिनट में समाप्त। किसी को न बताएँ।", bypass_quiet=True),
]}


def get(key: str) -> Event:
    if key in EVENTS:
        return EVENTS[key]
    # unknown events from older call sites still go out, by WhatsApp, with their own text
    return Event(key, key, key, G, ("whatsapp",), "{message}", "{message}")
