"""What the portal shows for one child, and the office-side decisions on portal requests (ADR-011)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.portal.models import ChangeRequest, StudentLeave


def section_of(child):
    enr = child.current_enrollment
    return enr.section if enr else None


def is_boarder(child, on: date | None = None) -> bool:
    from apps.hostel.models import Allocation

    return Allocation.objects.filter(student=child, check_out_date__isnull=True).exists()


# ------------------------------------------------------------------ read side
def today_attendance(child, on: date) -> str | None:
    from apps.attendance.models import AttendanceRecord

    st = list(AttendanceRecord.objects.filter(student=child, date=on).values_list("status", flat=True))
    if not st:
        return None
    if "absent" in st:
        return "absent" if all(s == "absent" for s in st) else "partly absent"
    return st[0] if len(set(st)) == 1 else "present"


def dues(child, on: date) -> dict:
    from apps.fees.selectors import students_with_dues
    from apps.people.models import Student

    s = students_with_dues(Student.objects.filter(pk=child.pk), on).first()
    z = Decimal("0.00")
    return {"charged": s.total_charged or z, "paid": s.total_paid or z, "outstanding": s.outstanding or z, "overdue": s.overdue or z}


def fee_detail(child, on: date) -> dict:
    from apps.fees.models import Charge, Receipt
    from apps.fees.selectors import charges_with_balance

    charges = charges_with_balance(Charge.objects.filter(student=child)).select_related("head").order_by("due_date", "pk")
    receipts = Receipt.objects.filter(student=child, cancelled_at__isnull=True).order_by("-date", "-sequence")
    return {
        **dues(child, on),
        "charges": [{"id": c.pk, "head": c.head.name, "description": c.description, "due_date": c.due_date, "amount": c.net,
                     "paid": c.paid, "outstanding": c.outstanding, "overdue": c.outstanding > 0 and c.due_date < on} for c in charges],
        "receipts": [{"id": r.pk, "number": r.number, "date": r.date, "amount": r.amount, "mode": r.get_mode_display()} for r in receipts],
    }


def published_exams(child):
    from apps.exam.models import Exam

    enr = child.current_enrollment
    progs = set(child.enrollments.values_list("program_id", flat=True))
    if enr:
        progs.add(enr.program_id)
    return Exam.objects.filter(program_id__in=progs, published_at__isnull=False).select_related("academic_year").order_by("-published_at")


def results(child) -> list[dict]:
    from apps.exam.services import exam_results

    out = []
    for exam in published_exams(child):
        row = next((r for r in exam_results(exam)["rows"] if r["student"] == child.pk), None)
        if row is None:
            continue
        out.append({"exam": exam.pk, "name": exam.name, "year": str(exam.academic_year), "published_at": exam.published_at,
                    "percentage": row.get("percentage"), "grade": row.get("grade"),
                    "result": "pending" if row.get("pending") else ("pass" if row.get("passed") else "fail"),
                    "rank_section": row.get("rank_section"),
                    "subjects": [{"name": s.get("name"), "marks": s.get("display"), "max": s.get("max"), "grade": s.get("grade")}
                                 for s in row.get("subjects", [])]})
    return out


def homework(child, *, upcoming_only=False, on: date | None = None) -> list[dict]:
    from apps.learning.models import Homework, Submission

    sec = section_of(child)
    if sec is None:
        return []
    qs = Homework.objects.filter(section=sec).select_related("subject").prefetch_related("files").order_by("-due_date", "-pk")
    if upcoming_only:
        qs = qs.filter(due_date__gte=on or timezone.localdate())
    subs = {s.homework_id: s for s in Submission.objects.filter(student=child, homework__in=qs).prefetch_related("files")}
    out = []
    for hw in qs[:100]:
        s = subs.get(hw.pk)
        out.append({"id": hw.pk, "subject": hw.subject.name, "title": hw.title, "description": hw.description, "due_date": hw.due_date,
                    "files": [{"id": f.pk, "name": f.original_name, "size": f.size} for f in hw.files.all()],
                    "status": "not submitted" if s is None else ("checked" if s.reviewed_at else "submitted"),
                    "submitted_at": s.submitted_at if s else None, "late": s.late if s else False,
                    "grade": s.grade if s else "", "remarks": s.remarks if s else "",
                    "my_files": [{"id": f.pk, "name": f.original_name} for f in s.files.all()] if s else [],
                    "text": s.text if s else ""})
    return out


def materials(child):
    from apps.learning.models import Material

    sec = section_of(child)
    if sec is None:
        return Material.objects.none()
    return Material.objects.filter(Q(section=sec) | Q(section__isnull=True, program=sec.program)).select_related("subject")


def notices(child, user):
    from apps.notify.models import Notice, NoticeRead

    qs = Notice.objects.filter(students=child, sent_at__isnull=False).order_by("-sent_at")
    read = set(NoticeRead.objects.filter(user=user, notice__in=qs).values_list("notice_id", flat=True))
    return qs, read


def home(child, user, on: date) -> dict:
    sec = section_of(child)
    qs, read = notices(child, user)
    latest = results(child)[:1]
    hw = [h for h in homework(child, upcoming_only=True, on=on) if h["status"] == "not submitted"]
    return {
        "child": {"id": child.pk, "name": child.full_name, "admission_no": child.admission_no,
                  "section": str(sec) if sec else None, "branch": child.branch.name, "boarder": is_boarder(child)},
        "attendance_today": today_attendance(child, on),
        "fees": dues(child, on),
        "latest_result": latest[0] if latest else None,
        "homework_due": hw[:5],
        "homework_due_count": len(hw),
        "notices_unread": sum(1 for n in qs if n.pk not in read),
        "notices": [{"id": n.pk, "title": n.title, "sent_at": n.sent_at, "read": n.pk in read} for n in qs[:3]],
    }


def transport(child, on: date) -> dict | None:
    from apps.transport.models import TransportAssignment

    a = (TransportAssignment.objects.filter(student=child, start_date__lte=on).filter(Q(end_date__isnull=True) | Q(end_date__gte=on))
         .select_related("route", "stop", "vehicle").first())
    if a is None:
        return None
    v = a.vehicle
    now = timezone.now()
    return {"route": a.route.name, "route_code": a.route.code, "stop": a.stop.name,
            "stop_lat": getattr(a.stop, "latitude", None), "stop_lng": getattr(a.stop, "longitude", None),
            "pickup_time": getattr(a.stop, "pickup_time", None), "drop_time": getattr(a.stop, "drop_time", None),
            "vehicle": v.registration_no, "driver": v.driver_name, "driver_phone": v.driver_phone,
            "helper": v.helper_name, "helper_phone": v.helper_phone, "monthly_fare": a.monthly_fare,
            "bus": {"lat": v.last_latitude, "lng": v.last_longitude, "speed": v.last_speed_kmph, "seen_at": v.last_seen_at,
                    "age_seconds": int((now - v.last_seen_at).total_seconds()) if v.last_seen_at else None}}


def mess_menu(child) -> dict | None:
    from apps.hostel.models import MenuItem, MessMember

    m = MessMember.objects.filter(student=child, end_date__isnull=True).select_related("mess").first()
    if m is None:
        return None
    items = MenuItem.objects.filter(mess=m.mess).order_by("day", "meal")
    return {"mess": m.mess.name, "items": [{"day": i.day, "day_name": i.get_day_display(), "meal": i.meal, "meal_name": i.get_meal_display(),
                                            "items": i.items, "items_hi": i.items_hi, "is_veg": i.is_veg} for i in items]}


# ------------------------------------------------------------------ leave (day scholars)
def on_leave_ids(student_ids, on: date) -> set[int]:
    return set(StudentLeave.objects.filter(student_id__in=student_ids, status=StudentLeave.Status.APPROVED,
                                           from_date__lte=on, to_date__gte=on).values_list("student_id", flat=True))


@transaction.atomic
def apply_leave(*, child, from_date: date, to_date: date, reason: str, by: str) -> StudentLeave:
    if to_date < from_date:
        raise Conflict("The leave ends before it starts.")
    if is_boarder(child):
        raise Conflict("Hostel students ask for an outpass instead.")
    if from_date < timezone.localdate() - timedelta(days=7):
        raise Conflict("Leave can be applied up to 7 days back.")
    if StudentLeave.objects.filter(student=child, status__in=["requested", "approved"], from_date__lte=to_date,
                                   to_date__gte=from_date).exists():
        raise Conflict("There is already a leave application for these dates.")
    lv = StudentLeave.objects.create(branch=child.branch, student=child, from_date=from_date, to_date=to_date,
                                     reason=reason.strip(), requested_by=by)
    sec = section_of(child)
    if sec is not None and sec.class_teacher_id and sec.class_teacher.user_id:
        from apps.core import notify

        notify.staff_users([sec.class_teacher.user], "portal.leave_requested",
                           f"Leave asked for {child.full_name} ({from_date:%d-%m} to {to_date:%d-%m}).",
                           branch=child.branch, student=child.full_name, from_date=f"{from_date:%d-%m-%Y}",
                           to_date=f"{to_date:%d-%m-%Y}")
    record("portal.leave_requested", actor=by, student=child.pk, leave=lv.pk)
    return lv


@transaction.atomic
def decide_leave(*, leave: StudentLeave, approve: bool, by: str, note: str = "") -> StudentLeave:
    from apps.attendance.models import AttendanceRecord

    lv = StudentLeave.objects.select_for_update().select_related("student").get(pk=leave.pk)
    if lv.status != StudentLeave.Status.REQUESTED:
        raise Conflict("This application has already been decided.")
    lv.status = StudentLeave.Status.APPROVED if approve else StudentLeave.Status.REJECTED
    lv.decided_by, lv.decided_at, lv.decision_note = by, timezone.now(), note.strip()
    lv.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    if approve:  # days already passed are recorded as leave unless the teacher marked them present
        today, d, sec = timezone.localdate(), lv.from_date, section_of(lv.student)
        while d <= min(lv.to_date, today):
            rec = AttendanceRecord.objects.filter(student=lv.student, date=d, period__isnull=True).first()
            if rec is None:
                AttendanceRecord.objects.create(branch=lv.branch, student=lv.student, section=sec, date=d, status="leave",
                                                marked_by=f"leave:{lv.pk}")
            elif rec.status == "absent":
                rec.status, rec.marked_by = "leave", f"leave:{lv.pk}"
                rec.save(update_fields=["status", "marked_by", "updated_at"])
            d += timedelta(days=1)
    from apps.core import notify

    notify.guardian(lv.student, "portal.leave_decided",
                    f"Leave for {lv.student.full_name} {lv.from_date:%d-%m} to {lv.to_date:%d-%m}: {lv.get_status_display()}.",
                    status=lv.get_status_display(), from_date=f"{lv.from_date:%d-%m-%Y}", to_date=f"{lv.to_date:%d-%m-%Y}")
    record("portal.leave_decided", actor=by, leave=lv.pk, status=lv.status)
    return lv


# ------------------------------------------------------------------ change requests
def current_value(child, field: str, guardian) -> str:
    if field == ChangeRequest.Field.ADDRESS:
        return child.address or (guardian.address if guardian else "")
    if field == ChangeRequest.Field.PHONE:
        return guardian.phone if guardian else ""
    return guardian.email if guardian else ""


@transaction.atomic
def ask_change(*, child, guardian, field: str, new_value: str, by: str) -> ChangeRequest:
    from apps.portal.access import digits

    v = new_value.strip()
    if field == ChangeRequest.Field.PHONE:
        if len(digits(v)) != 10:
            raise Conflict("Give a 10-digit mobile number.")
        v = digits(v)
    if field == ChangeRequest.Field.EMAIL and ("@" not in v or " " in v):
        raise Conflict("Give a valid email address.")
    if not v:
        raise Conflict("Give the new value.")
    if ChangeRequest.objects.filter(student=child, field=field, status=ChangeRequest.Status.REQUESTED).exists():
        raise Conflict("A change for this is already waiting for the office.")
    cr = ChangeRequest.objects.create(branch=child.branch, student=child, guardian=guardian, field=field,
                                      old_value=current_value(child, field, guardian), new_value=v, requested_by=by)
    record("portal.change_requested", actor=by, student=child.pk, field=field)
    return cr


@transaction.atomic
def decide_change(*, request: ChangeRequest, approve: bool, by: str, note: str = "") -> ChangeRequest:
    cr = ChangeRequest.objects.select_for_update(of=("self",)).select_related("student", "guardian").get(pk=request.pk)
    if cr.status != ChangeRequest.Status.REQUESTED:
        raise Conflict("This request has already been decided.")
    cr.status = ChangeRequest.Status.APPROVED if approve else ChangeRequest.Status.REJECTED
    cr.decided_by, cr.decided_at, cr.decision_note = by, timezone.now(), note.strip()
    cr.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    if approve:
        g = cr.guardian
        if cr.field == ChangeRequest.Field.ADDRESS:
            cr.student.address = cr.new_value
            cr.student.save(update_fields=["address", "updated_at"])
            if g:
                g.address = cr.new_value
                g.save(update_fields=["address", "updated_at"])
        elif g is None:
            raise Conflict("The parent's record is missing; update it from the student's page.")
        elif cr.field == ChangeRequest.Field.PHONE:
            from apps.accounts.models import User
            from apps.portal.access import digits, guardians_with_phone

            old = digits(g.phone)
            g.phone = cr.new_value
            g.save(update_fields=["phone", "updated_at"])
            # The portal login follows the number. If another child's record still has the old number,
            # that login keeps it (and that child); the new number gets its own login at first OTP.
            if old and not guardians_with_phone(old).exists():
                User.objects.filter(phone=old, email__endswith="@parents.eraj.local").update(phone=digits(cr.new_value))
        else:
            g.email = cr.new_value
            g.save(update_fields=["email", "updated_at"])
    record("portal.change_decided", actor=by, request=cr.pk, field=cr.field, status=cr.status)
    return cr


# ------------------------------------------------------------------ student logins
@transaction.atomic
def create_student_login(*, student, email: str, password: str, by: str):
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError

    from apps.accounts.models import User
    from apps.org.models import Role, RoleAssignment

    if student.user_id:
        raise Conflict("This student already has a login.")
    email = email.strip().lower()
    if User.objects.filter(email__iexact=email).exists():
        raise Conflict("That email is already used by another login.")
    user = User(email=email, first_name=student.full_name.split(" ")[0][:150])
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise Conflict(" ".join(exc.messages)) from exc
    user.set_password(password)
    user.save()
    student.user = user
    student.save(update_fields=["user", "updated_at"])
    RoleAssignment.objects.create(user=user, role=Role.STUDENT, branch=student.branch)
    record("portal.student_login_created", actor=by, student=student.pk)
    return user


@transaction.atomic
def remove_student_login(*, student, by: str) -> None:
    from apps.org.models import Role, RoleAssignment

    if not student.user_id:
        raise Conflict("This student has no login.")
    user = student.user
    RoleAssignment.objects.filter(user=user, role=Role.STUDENT).delete()
    user.is_active = False
    user.save(update_fields=["is_active"])
    student.user = None
    student.save(update_fields=["user", "updated_at"])
    record("portal.student_login_removed", actor=by, student=student.pk)
