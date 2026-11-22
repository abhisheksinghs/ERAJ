"""Homework, submissions, online classes and tests (ADR-011)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.learning.models import Attempt, Homework, JoinRecord, OnlineClass, OnlineTest, Submission
from apps.people.models import Enrollment, Student, TeachingAssignment

JOIN_EARLY = timedelta(minutes=15)
GRACE = timedelta(seconds=30)


def section_students(section):
    return Student.objects.filter(status="active", enrollments__section=section,
                                  enrollments__status=Enrollment.Status.ACTIVE).distinct().order_by("full_name")


def student_section(student):
    enr = student.current_enrollment
    return enr.section if enr else None


def may_teach(staff, section, subject) -> bool:
    if staff is None:
        return False
    return TeachingAssignment.objects.filter(staff=staff, section=section, subject=subject).exists()


def check_teacher(*, staff, section, subject, any_section: bool) -> None:
    if any_section:
        return
    if not may_teach(staff, section, subject):
        raise Conflict(f"You don't teach {subject} to {section}.")


def due_end(hw: Homework) -> datetime:
    return timezone.make_aware(datetime.combine(hw.due_date, time(23, 59, 59)))


# ------------------------------------------------------------------ homework
def homework_set(hw: Homework) -> None:
    """Alert the section's parents (learning.homework_set)."""
    from apps.notify.services import raise_event

    for s in section_students(hw.section):
        with transaction.atomic():
            raise_event(branch=hw.branch, event="learning.homework_set", student=s,
                        context={"subject": hw.subject.name, "title": hw.title, "due_date": hw.due_date.strftime("%d-%m-%Y")},
                        dedupe=f"hw:{hw.pk}:{s.pk}")


@transaction.atomic
def submit(*, homework: Homework, student, text: str = "", files=(), now: datetime | None = None) -> Submission:
    now = now or timezone.now()
    if student_section(student) != homework.section:
        raise Conflict("This homework is for another section.")
    sub = Submission.objects.select_for_update().filter(homework=homework, student=student).first()
    if sub and sub.reviewed_at:
        raise Conflict("Your teacher has already checked this; it can't be changed.")
    if not text.strip() and not files and not (sub and sub.files.exists()):
        raise Conflict("Write an answer or attach a photo or file.")
    late = now > due_end(homework)
    if sub is None:
        sub = Submission.objects.create(branch=homework.branch, homework=homework, student=student, text=text,
                                        submitted_at=now, late=late)
    else:
        sub.text, sub.submitted_at, sub.late = text or sub.text, now, late
        sub.save(update_fields=["text", "submitted_at", "late", "updated_at"])
    from apps.core.files import content_type
    from apps.learning.models import SubmissionFile

    for f in files:
        SubmissionFile.objects.create(submission=sub, file=f, original_name=f.name[:255], content_type=content_type(f.name), size=f.size)
    record("learning.submitted", actor=f"student:{student.pk}", homework=homework.pk, late=late)
    return sub


@transaction.atomic
def grade(*, submission: Submission, grade: str, remarks: str, by: str) -> Submission:
    sub = Submission.objects.select_for_update().get(pk=submission.pk)
    if not grade.strip() and not remarks.strip():
        raise Conflict("Give a grade or a remark.")
    sub.grade, sub.remarks, sub.reviewed_by, sub.reviewed_at = grade.strip(), remarks.strip(), by, timezone.now()
    sub.save(update_fields=["grade", "remarks", "reviewed_by", "reviewed_at", "updated_at"])
    record("learning.graded", actor=by, submission=sub.pk, grade=sub.grade)
    return sub


# ------------------------------------------------------------------ online classes
@transaction.atomic
def join(*, online_class: OnlineClass, student, now: datetime | None = None) -> str:
    now = now or timezone.now()
    if student_section(student) != online_class.section:
        raise Conflict("This class is for another section.")
    if now < online_class.starts_at - JOIN_EARLY:
        raise Conflict(f"The class opens at {timezone.localtime(online_class.starts_at):%H:%M}.")
    if now > online_class.ends_at:
        raise Conflict("This class has ended.")
    try:
        with transaction.atomic():
            JoinRecord.objects.create(online_class=online_class, student=student, first_opened_at=now)
    except IntegrityError:
        JoinRecord.objects.filter(online_class=online_class, student=student).update(opens=F("opens") + 1)
    return online_class.link


def classes_on(section, day: date):
    start = timezone.make_aware(datetime.combine(day, time.min))
    return OnlineClass.objects.filter(section=section, starts_at__gte=start, starts_at__lt=start + timedelta(days=1)).select_related("subject")


# ------------------------------------------------------------------ tests
def _score(test: OnlineTest, answers: dict) -> tuple[Decimal, Decimal]:
    score = total = Decimal("0")
    for q in test.questions.all():
        total += q.marks
        a = answers.get(str(q.pk))
        if a is not None and str(a).isdigit() and int(a) == q.correct:
            score += q.marks
    return score, total


@transaction.atomic
def start_attempt(*, test: OnlineTest, student, now: datetime | None = None) -> Attempt:
    now = now or timezone.now()
    if student_section(student) != test.section:
        raise Conflict("This test is for another section.")
    if not test.published:
        raise Conflict("This test isn't open yet.")
    a = Attempt.objects.select_for_update().filter(test=test, student=student).first()
    if a is not None:
        return a
    if now < test.opens_at:
        raise Conflict(f"The test opens at {timezone.localtime(test.opens_at):%d-%m %H:%M}.")
    if now >= test.closes_at:
        raise Conflict("The test has closed.")
    if not test.questions.exists():
        raise Conflict("This test has no questions.")
    deadline = min(now + timedelta(minutes=test.time_limit_minutes), test.closes_at)
    return Attempt.objects.create(branch=test.branch, test=test, student=student, started_at=now, deadline=deadline)


@transaction.atomic
def submit_attempt(*, attempt: Attempt, answers: dict, now: datetime | None = None) -> Attempt:
    now = now or timezone.now()
    a = Attempt.objects.select_for_update().select_related("test").get(pk=attempt.pk)
    if a.submitted_at:
        raise Conflict("Already submitted.")
    valid = {str(q.pk): q for q in a.test.questions.all()}
    clean = {}
    for k, v in (answers or {}).items():
        q = valid.get(str(k))
        if q is not None and str(v).isdigit() and 0 <= int(v) < len(q.options):
            clean[str(k)] = int(v)
    a.answers = clean
    a.auto_submitted = now > a.deadline + GRACE
    a.score, a.max_score = _score(a.test, clean)
    a.submitted_at = min(now, a.deadline + GRACE)
    a.save(update_fields=["answers", "auto_submitted", "score", "max_score", "submitted_at", "updated_at"])
    record("learning.test_submitted", actor=f"student:{a.student_id}", test=a.test_id, score=str(a.score))
    return a


def close_expired(test: OnlineTest, now: datetime | None = None) -> int:
    """Score attempts whose time ran out without a submit (what was saved counts)."""
    now = now or timezone.now()
    n = 0
    for a in Attempt.objects.filter(test=test, submitted_at__isnull=True, deadline__lt=now - GRACE):
        submit_attempt(attempt=a, answers=a.answers, now=now)
        n += 1
    return n


def test_results(test: OnlineTest) -> dict:
    close_expired(test)
    attempts = {a.student_id: a for a in test.attempts.all()}
    rows = []
    for s in section_students(test.section):
        a = attempts.get(s.pk)
        rows.append({"student": s.pk, "name": s.full_name, "admission_no": s.admission_no,
                     "status": "not taken" if a is None else ("in progress" if a.submitted_at is None else "submitted"),
                     "score": a.score if a else None, "max_score": a.max_score if a else None,
                     "auto_submitted": a.auto_submitted if a else False})
    scored = [r["score"] for r in rows if r["score"] is not None]
    return {"test": test.pk, "title": test.title, "rows": rows, "taken": len(scored),
            "average": (sum(scored) / len(scored)).quantize(Decimal("0.01")) if scored else None}


# ------------------------------------------------------------------ reports
def submission_rates(*, branch, start: date, end: date, section=None) -> list[dict]:
    qs = Homework.objects.filter(branch=branch, due_date__range=(start, end)).select_related("section__program", "subject")
    if section is not None:
        qs = qs.filter(section=section)
    by_section: dict = {}
    for hw in qs.annotate(n=Count("submissions"), n_late=Count("submissions", filter=Q(submissions__late=True))):
        expected = section_students(hw.section).count()
        row = by_section.setdefault(hw.section_id, {"section": str(hw.section), "homework": 0, "expected": 0, "submitted": 0, "late": 0})
        row["homework"] += 1
        row["expected"] += expected
        row["submitted"] += hw.n
        row["late"] += hw.n_late
    for row in by_section.values():
        row["rate"] = round(100 * row["submitted"] / row["expected"]) if row["expected"] else 0
    return sorted(by_section.values(), key=lambda r: r["section"])


def student_rates(*, section, start: date, end: date) -> list[dict]:
    hws = list(Homework.objects.filter(section=section, due_date__range=(start, end)))
    subs = Submission.objects.filter(homework__in=hws)
    done = {}
    for sid, late in subs.values_list("student_id", "late"):
        d = done.setdefault(sid, [0, 0])
        d[0] += 1
        d[1] += int(late)
    rows = []
    for s in section_students(section):
        n, late = done.get(s.pk, [0, 0])
        rows.append({"student": s.pk, "name": s.full_name, "homework": len(hws), "submitted": n, "late": late,
                     "pending": len(hws) - n, "rate": round(100 * n / len(hws)) if hws else 0})
    return rows


def pending(*, branch, on: date | None = None) -> list[dict]:
    on = on or timezone.localdate()
    out = []
    for hw in Homework.objects.filter(branch=branch, due_date__lt=on).select_related("section", "subject").order_by("-due_date")[:200]:
        done = set(hw.submissions.values_list("student_id", flat=True))
        missing = [s.full_name for s in section_students(hw.section) if s.pk not in done]
        if missing:
            out.append({"homework": hw.pk, "title": hw.title, "section": str(hw.section), "subject": hw.subject.name,
                        "due_date": hw.due_date, "missing": len(missing), "students": ", ".join(missing[:30])})
    return out


def test_scores(*, branch, section=None) -> list[dict]:
    qs = OnlineTest.objects.filter(branch=branch).select_related("section", "subject")
    if section is not None:
        qs = qs.filter(section=section)
    out = []
    for t in qs:
        res = test_results(t)
        out.append({"test": t.pk, "title": t.title, "section": str(t.section), "subject": t.subject.name,
                    "opens_at": t.opens_at, "taken": res["taken"], "of": len(res["rows"]), "average": res["average"]})
    return out
