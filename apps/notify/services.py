"""Raising and sending alerts (ADR-011).

    raise_event(branch=b, event="attendance.absent", student=s, context={"date": "20-11-2026"})
    raise_event(branch=b, event="inventory.low_stock", role="store", context={"message": "…"})

Rows go into `Message` (the delivery log) inside the caller's transaction; sending happens on a
Celery worker after commit, so a provider outage never blocks marking attendance or a receipt.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.notify import catalogue, providers
from apps.notify.models import AlertRule, Channel, ChannelConfig, Message, Notice, NotifySettings, OptOut, Template

S = Message.Status


class _Safe(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def settings_for(branch) -> NotifySettings:
    obj, _ = NotifySettings.objects.get_or_create(branch=branch)
    return obj


def config_for(branch, channel: str) -> ChannelConfig:
    cfg = ChannelConfig.objects.filter(branch=branch, channel=channel).first()
    if cfg is None:
        enabled = channel != Channel.SMS  # SMS waits for DLT approval (scope)
        cfg, _ = ChannelConfig.objects.get_or_create(branch=branch, channel=channel, defaults={"enabled": enabled})
    return cfg


def rule_for(branch, event: str):
    ev = catalogue.get(event)
    rule = AlertRule.objects.filter(branch=branch, event=event).first()
    if rule is None:
        return ev.enabled, list(ev.channels)
    return rule.enabled, list(rule.channels or ev.channels)


def effective_channels(branch, wanted: list[str]) -> list[str]:
    """SMS falls back to WhatsApp + email while SMS is off (DLT pending)."""
    out = []
    for ch in wanted:
        if ch == Channel.SMS and not config_for(branch, Channel.SMS).enabled:
            if settings_for(branch).sms_fallback:
                out += [Channel.WHATSAPP, Channel.EMAIL]
            continue
        if config_for(branch, ch).enabled:
            out.append(ch)
    seen = []
    for ch in out:
        if ch not in seen:
            seen.append(ch)
    return seen


def render(branch, event: str, channel: str, language: str, context: dict) -> tuple[str, str]:
    t = (Template.objects.filter(branch=branch, event=event, channel=channel, language=language).first()
         or Template.objects.filter(branch=branch, event=event, channel=channel, language="en").first())
    ev = catalogue.get(event)
    body = t.body if t else (ev.hi if language == "hi" else ev.en)
    ctx = _Safe({"school": branch.name, **{k: ("" if v is None else v) for k, v in context.items()}})
    return body.format_map(ctx).strip(), (t.provider_template if t else "")


def in_quiet_hours(branch, at: datetime) -> datetime | None:
    """The time to send instead, or None when sending now is fine."""
    cfg = settings_for(branch)
    local = timezone.localtime(at)
    t = local.time()
    qs, qe = cfg.quiet_start, cfg.quiet_end
    if qs == qe:
        return None
    quiet = (qs <= t or t < qe) if qs > qe else (qs <= t < qe)
    if not quiet:
        return None
    day = local.date() if t < qe else local.date() + timedelta(days=1)
    return timezone.make_aware(datetime.combine(day, qe))


def _guardian_targets(student):
    links = list(student.guardian_links.select_related("guardian__user").all())
    link = next((g for g in links if g.is_primary), links[0] if links else None)
    return [link.guardian] if link else []


def _staff_targets(branch, role: str):
    from apps.org.models import RoleAssignment

    return [ra.user for ra in RoleAssignment.objects.filter(branch=branch, role=role).select_related("user")]


def _contact(channel: str, phone: str, email: str) -> str:
    return email if channel == Channel.EMAIL else phone


def _queue(msgs: list[Message]) -> None:
    schema = connection.schema_name
    ids = [m.pk for m in msgs if m.status == S.QUEUED]
    if not ids:
        return

    def go():
        import logging

        from apps.notify.tasks import send_message

        for pk in ids:
            try:
                send_message.delay(schema, pk)
            except Exception:  # broker down: the row stays queued; release_held re-queues it (ADR-011)
                logging.getLogger("eraj.notify").exception("could not queue message %s", pk)

    transaction.on_commit(go)


def raise_event(*, branch, event: str, context: dict | None = None, student=None, role: str | None = None,
                users=None, to_phone: str = "", dedupe: str = "", notice: Notice | None = None,
                channels: list[str] | None = None) -> list[Message]:
    """Create log rows for an event and queue them. Returns the rows (skipped ones included)."""
    ev = catalogue.get(event)
    enabled, wanted = rule_for(branch, event)
    if not enabled and ev.audience != "direct":
        return []
    chans = effective_channels(branch, channels if channels is not None else wanted)
    context = dict(context or {})
    now = timezone.now()
    hold_until = None if ev.bypass_quiet else in_quiet_hours(branch, now)
    targets = []  # (name, phone, email, language, guardian, user)
    if ev.audience == "direct":
        targets.append(("", to_phone, "", "en", None, None))
    elif users is not None or role:
        for u in (users if users is not None else _staff_targets(branch, role)):
            targets.append((u.get_full_name() or u.email, u.phone, u.email, u.preferred_language, None, u))
    elif student is not None:
        context.setdefault("student", student.full_name)
        for g in _guardian_targets(student):
            lang = g.user.preferred_language if g.user_id else "en"
            targets.append((g.full_name, g.phone, g.email, lang, g, None))
    out = []
    opted = set()
    guardians = [t[4] for t in targets if t[4] is not None]
    if guardians:
        opted = set(OptOut.objects.filter(guardian__in=guardians).values_list("guardian_id", "channel"))
    for name, phone, email, lang, guardian, user in targets:
        for ch in chans:
            to = _contact(ch, phone, email)
            if not to and (ch == Channel.EMAIL or ev.audience == "direct"):
                continue  # email is an extra channel; no address, no row
            body, ptpl = render(branch, event, ch, lang, context)
            status, error = S.QUEUED, ""
            if not to:
                status, error = S.SKIPPED, "No phone/email on record"
            elif guardian is not None and (guardian.pk, ch) in opted and event != "portal.otp":
                status, error = S.SKIPPED, "Opted out"
            elif hold_until is not None:
                status = S.HELD
            try:
                with transaction.atomic():
                    m = Message.objects.create(
                        branch=branch, event=event, channel=ch, to=to or "-", recipient_name=name, guardian=guardian,
                        student=student, user=user, notice=notice, language=lang, body=body, provider_template=ptpl,
                        status=status, error=error, send_after=hold_until if status == S.HELD else None,
                        dedupe_key=dedupe if to else "", bypass_quiet=ev.bypass_quiet)
            except IntegrityError:
                continue  # already raised today for this recipient
            out.append(m)
    _queue(out)
    return out


# ------------------------------------------------------------------ sending
SECRET_EVENTS = {"portal.otp"}


def redact(text: str) -> str:
    """Login codes never stay readable in the delivery log."""
    import re

    return re.sub(r"\d{4,8}", "••••••", text)


def _forget_secret(m: Message) -> None:
    if m.event in SECRET_EVENTS and m.status not in (S.QUEUED, S.HELD):
        Message.objects.filter(pk=m.pk).update(body=redact(m.body))


def send_now(message_id: int) -> Message:
    """Worker side: one attempt. Raises providers.Transient to let Celery retry."""
    with transaction.atomic():
        m = Message.objects.select_for_update().select_related("branch").get(pk=message_id)
        if m.status not in (S.QUEUED, S.HELD):
            return m
        if m.status == S.HELD and m.send_after and m.send_after > timezone.now():
            return m
        cfg = config_for(m.branch, m.channel)
        m.attempts += 1
        m.provider = cfg.provider
        m.save(update_fields=["attempts", "provider", "updated_at"])
    if not cfg.enabled:
        res = providers.Result("failed", error=f"{m.get_channel_display()} is switched off for this branch.")
    else:
        res = providers.SEND[cfg.provider](m, cfg)
    now = timezone.now()
    m.status, m.provider_ref, m.error = res.status, res.ref, res.error
    m.sent_at = now if res.status in (S.SENT, S.DELIVERED, S.SIMULATED) else None
    if res.status in (S.DELIVERED, S.SIMULATED):
        m.delivered_at = now
    m.save(update_fields=["status", "provider_ref", "error", "sent_at", "delivered_at", "updated_at"])
    _forget_secret(m)
    return m


def mark_failed_after_retries(message_id: int, reason: str) -> None:
    Message.objects.filter(pk=message_id, status__in=[S.QUEUED, S.HELD]).update(
        status=S.FAILED, error=f"Gave up after retries: {reason}"[:500], updated_at=timezone.now())
    for m in Message.objects.filter(pk=message_id, event__in=SECRET_EVENTS):
        _forget_secret(m)


def release_held(now: datetime | None = None) -> int:
    """Quiet hours over: send what was held."""
    now = now or timezone.now()
    ids = list(Message.objects.filter(status=S.HELD, send_after__lte=now).values_list("pk", flat=True))
    Message.objects.filter(pk__in=ids).update(status=S.QUEUED, updated_at=now)
    # also anything left queued for 10+ minutes (broker was down, worker restarted mid-send)
    stale = list(Message.objects.filter(status=S.QUEUED, updated_at__lt=now - timedelta(minutes=10)).values_list("pk", flat=True))
    msgs = list(Message.objects.filter(pk__in=set(ids) | set(stale)))
    _queue(msgs)
    return len(msgs)


def apply_receipt(*, provider_ref: str, status: str, error: str = "", at: datetime | None = None) -> int:
    """Delivery receipt from a provider webhook."""
    at = at or timezone.now()
    qs = Message.objects.filter(provider_ref=provider_ref).exclude(provider_ref="")
    if status == "delivered" or status == "read":
        return qs.exclude(status=S.FAILED).update(status=S.DELIVERED, delivered_at=at, updated_at=timezone.now())
    if status == "failed":
        return qs.update(status=S.FAILED, error=(error or "Provider reported failure")[:500], updated_at=timezone.now())
    if status == "sent":
        return qs.filter(status=S.QUEUED).update(status=S.SENT, updated_at=timezone.now())
    return 0


# ------------------------------------------------------------------ module hooks
def absent_today(*, student, on: date) -> None:
    raise_event(branch=student.branch, event="attendance.absent", student=student,
                context={"date": on.strftime("%d-%m-%Y")}, dedupe=f"absent:{student.pk}:{on:%Y%m%d}")


def daily_reminders(branch, today: date | None = None) -> dict:
    """Fee due in N days, fee overdue (weekly), library overdue (weekly)."""
    from apps.fees.models import Charge
    from apps.fees.selectors import charges_with_balance

    today = today or timezone.localdate()
    counts = Counter()
    days = (AlertRule.objects.filter(branch=branch, event="fees.due_soon").values_list("days_before", flat=True).first() or 3)
    soon = charges_with_balance(Charge.objects.filter(branch=branch, due_date=today + timedelta(days=days))).filter(outstanding__gt=0)
    for c in soon.select_related("student"):
        counts["due_soon"] += len(raise_event(branch=branch, event="fees.due_soon", student=c.student,
                                              context={"amount": f"{c.outstanding:,.0f}", "due_date": c.due_date.strftime("%d-%m-%Y")},
                                              dedupe=f"due:{c.pk}"))
    if today.weekday() == 0:  # overdue and library reminders once a week (Monday)
        late = charges_with_balance(Charge.objects.filter(branch=branch, due_date__lt=today)).filter(outstanding__gt=0)
        per_student: dict = {}
        for c in late.select_related("student"):
            row = per_student.setdefault(c.student_id, [c.student, 0, c.due_date])
            row[1] += c.outstanding
            row[2] = min(row[2], c.due_date)
        for student, amount, due in per_student.values():
            counts["overdue"] += len(raise_event(branch=branch, event="fees.overdue", student=student,
                                                 context={"amount": f"{amount:,.0f}", "due_date": due.strftime("%d-%m-%Y")},
                                                 dedupe=f"overdue:{student.pk}:{today:%Y%W}"))
        try:
            from apps.library.models import Issue

            for i in Issue.objects.filter(branch=branch, returned_at__isnull=True, due_date__lt=today,
                                          member__student__isnull=False).select_related("member__student", "book"):
                counts["library"] += len(raise_event(branch=branch, event="library.overdue", student=i.member.student,
                                                     context={"book": i.book.title, "due_date": i.due_date.strftime("%d-%m-%Y")},
                                                     dedupe=f"lib:{i.pk}:{today:%Y%W}"))
        except Exception as exc:  # never let the library reminder break fee reminders
            record("notify.library_reminder_skipped", reason=str(exc)[:200])
    return dict(counts)


# ------------------------------------------------------------------ notices
def audience_students(notice: Notice):
    from apps.people.models import Enrollment, Student

    active = Student.objects.filter(branch=notice.branch, status="active")
    a = Notice.Audience
    if notice.audience == a.SECTION:
        return active.filter(enrollments__section=notice.section, enrollments__status=Enrollment.Status.ACTIVE).distinct()
    if notice.audience == a.PROGRAM:
        return active.filter(enrollments__program=notice.program, enrollments__status=Enrollment.Status.ACTIVE,
                             enrollments__academic_year__is_current=True).distinct()
    if notice.audience == a.ROUTE:
        today = timezone.localdate()
        return active.filter(Q(transport__route=notice.route), Q(transport__end_date__isnull=True) | Q(transport__end_date__gte=today)).distinct()
    if notice.audience == a.BLOCK:
        return active.filter(hostel_allocations__room__block=notice.block, hostel_allocations__check_out_date__isnull=True).distinct()
    if notice.audience == a.PARENTS:
        return active
    return Student.objects.none()


@transaction.atomic
def send_notice(*, notice: Notice, by: str) -> Notice:
    n = Notice.objects.select_for_update().get(pk=notice.pk)
    if n.sent_at:
        raise Conflict("This notice has already been sent.")
    need = {"section": n.section_id, "program": n.program_id, "route": n.route_id, "block": n.block_id}
    if n.audience in need and not need[n.audience]:
        raise Conflict(f"Choose the {n.audience} for this notice.")
    ctx = {"title": n.title, "body": n.body}
    count = 0
    if n.audience == Notice.Audience.STAFF:
        from apps.accounts.models import User
        from apps.org.models import RoleAssignment

        staff_roles = ["admin", "accountant", "teacher", "librarian", "warden", "transport", "hr", "store"]
        users = User.objects.filter(pk__in=RoleAssignment.objects.filter(branch=n.branch, role__in=staff_roles).values("user"))
        count = users.count()
        if n.channels:
            raise_event(branch=n.branch, event="notice", users=list(users), context=ctx, notice=n, channels=list(n.channels))
    else:
        students = list(audience_students(n))
        n.students.set(students)
        count = len(students)
        if n.channels:
            for s in students:
                raise_event(branch=n.branch, event="notice", student=s, context=ctx, notice=n, channels=list(n.channels),
                            dedupe=f"notice:{n.pk}:{s.pk}")
    n.sent_at, n.sent_by, n.recipients = timezone.now(), by, count
    n.save(update_fields=["sent_at", "sent_by", "recipients", "updated_at"])
    record("notify.notice_sent", actor=by, notice=n.pk, audience=n.audience, recipients=count)
    return n


# ------------------------------------------------------------------ reports
def monthly_counts(branch, months: int = 6) -> list[dict]:
    from zoneinfo import ZoneInfo

    from django.db.models.functions import TruncMonth

    start = (timezone.localdate().replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    rows = (Message.objects.filter(branch=branch, created_at__date__gte=start)
            .annotate(m=TruncMonth("created_at", tzinfo=ZoneInfo("Asia/Kolkata")))
            .values("m", "channel", "status").annotate(n=Count("id")))
    out: dict = {}
    for r in rows:
        month = r["m"].strftime("%Y-%m")
        row = out.setdefault((month, r["channel"]), {"month": month, "channel": r["channel"], "total": 0})
        row[r["status"]] = r["n"]
        row["total"] += r["n"]
    return sorted(out.values(), key=lambda x: (x["month"], x["channel"]), reverse=True)


