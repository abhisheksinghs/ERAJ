"""Parent / student portal API (ADR-011).

Every child endpoint goes through `access.child_for` (404 for anyone else's child) and reads only
that child's rows. Work a student does themself (submit homework, join a class, take a test) needs
the student's own login; a parent can see it but not do it for them.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import SchemaScopedTokenObtainPairSerializer
from apps.core.files import LEARNING, check_upload, download
from apps.org.mixins import BranchScopedViewSetMixin, PermissionedViewSetMixin
from apps.org.permissions import request_can
from apps.org.scope import resolve_scope
from apps.people.models import Student
from apps.portal import access, otp, services
from apps.portal.models import ChangeRequest, StudentLeave
from apps.portal.serializers import (
    ChangeAskSerializer, ChangeRequestSerializer, DecideSerializer, LeaveAskSerializer, OtpRequestSerializer,
    OtpVerifySerializer, OutpassAskSerializer, StudentLeaveSerializer, StudentLoginCreateSerializer, StudentLoginSerializer,
)


def who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


def client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR")


# ------------------------------------------------------------------ login
class OtpRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "otp"

    @extend_schema(request=OtpRequestSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        s = OtpRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(otp.request_code(phone=s.validated_data["phone"], ip=client_ip(request)))


class OtpVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "otp"

    @extend_schema(request=OtpVerifySerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        s = OtpVerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = otp.verify_code(phone=s.validated_data["phone"], code=s.validated_data["code"])
        refresh = SchemaScopedTokenObtainPairSerializer.get_token(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})


class MeView(APIView):
    """The caller's children (or themself, for a student login). Spans branches, so no X-Branch."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        kids = list(access.children_qs(request.user))
        rows = []
        for c in kids:
            sec = services.section_of(c)
            rows.append({"id": c.pk, "name": c.full_name, "admission_no": c.admission_no, "section": str(sec) if sec else None,
                         "branch": c.branch_id, "branch_name": c.branch.name, "is_self": access.is_self(request, c)})
        u = request.user
        return Response({"name": u.get_full_name() or u.email, "phone": u.phone, "language": u.preferred_language,
                         "kind": "student" if any(r["is_self"] for r in rows) else "parent", "children": rows})


# ------------------------------------------------------------------ one child
class ChildViewSet(PermissionedViewSetMixin, viewsets.GenericViewSet):
    perm_resource = "portal.child"
    lookup_value_regex = r"\d+"
    action_perms = {a: "portal.child.act" for a in
                    ("submit", "join", "start_test", "save_answers", "finish_test", "outpass", "read_notice", "leave", "change")}
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def child(self):
        return access.child_for(self.request, self.kwargs["pk"])

    def own(self, child):
        if not access.is_self(self.request, child):
            raise PermissionDenied("Only the student's own login can do this.")

    def today(self):
        return timezone.localdate()

    def _date(self, name, default):
        raw = self.request.query_params.get(name)
        if not raw:
            return default
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise ValidationError({name: "Use YYYY-MM-DD."}) from exc

    def _int(self, name, source=None):
        raw = (source if source is not None else self.request.query_params).get(name)
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError({name: "Required."}) from exc

    # -- home and records ------------------------------------------------
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request, pk=None):
        return Response(services.home(self.child(), request.user, self.today()))

    @extend_schema(parameters=[OpenApiParameter("month", str, description="YYYY-MM")], responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def attendance(self, request, pk=None):
        from apps.attendance.services import student_calendar

        child = self.child()
        raw = request.query_params.get("month")
        try:
            start = date.fromisoformat(f"{raw}-01") if raw else self.today().replace(day=1)
        except ValueError as exc:
            raise ValidationError({"month": "Use YYYY-MM."}) from exc
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        return Response(student_calendar(student=child, start=start, end=min(end, max(self.today(), start))))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def fees(self, request, pk=None):
        return Response(services.fee_detail(self.child(), self.today()))

    @extend_schema(parameters=[OpenApiParameter("receipt", int)], responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        from apps.fees.models import Receipt
        from apps.fees.pdf import receipt_pdf

        r = Receipt.objects.filter(student=self.child(), pk=self._int("receipt"), cancelled_at__isnull=True).first()
        if r is None:
            raise NotFound()
        resp = HttpResponse(receipt_pdf(r, duplicate=r.print_count > 0), content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{r.number.replace("/", "-")}.pdf"'
        return resp

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        return Response(services.results(self.child()))

    @extend_schema(parameters=[OpenApiParameter("exam", int)], responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="report-card")
    def report_card(self, request, pk=None):
        from apps.exam import pdf
        from apps.exam.services import exam_results

        child = self.child()
        exam = services.published_exams(child).filter(pk=self._int("exam")).first()
        if exam is None:  # unpublished (or not this child's class): same answer as a missing exam
            raise NotFound()
        res = exam_results(exam)
        rows = [r for r in res["rows"] if r["student"] == child.pk]
        if not rows:
            raise NotFound()
        resp = HttpResponse(pdf.report_cards_pdf(exam=exam, result=res, rows=rows), content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="report-card-{exam.pk}-{child.admission_no}.pdf"'
        return resp

    @extend_schema(parameters=[OpenApiParameter("date", str)], responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def timetable(self, request, pk=None):
        from apps.timetable.services import section_grid

        sec = services.section_of(self.child())
        if sec is None:
            return Response({"title": None, "days": [], "slots": [], "cells": [], "online": []})
        return Response(section_grid(sec, self._date("date", self.today())))

    @extend_schema(parameters=[OpenApiParameter("from", str), OpenApiParameter("to", str)], responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def diary(self, request, pk=None):
        from apps.learning.models import DiaryEntry

        sec = services.section_of(self.child())
        end = self._date("to", self.today())
        start = self._date("from", end - timedelta(days=13))
        rows = [] if sec is None else DiaryEntry.objects.filter(section=sec, date__range=(start, end)).select_related("subject", "teacher")
        return Response([{"id": d.pk, "date": d.date, "period": d.period, "subject": d.subject.name, "topic": d.topic, "notes": d.notes,
                          "teacher": d.teacher.full_name if d.teacher else ""} for d in rows])

    # -- homework and material --------------------------------------------
    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def homework(self, request, pk=None):
        return Response(services.homework(self.child()))

    @extend_schema(parameters=[OpenApiParameter("homework", int), OpenApiParameter("file", int)],
                   responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="homework-file")
    def homework_file(self, request, pk=None):
        from apps.learning.models import HomeworkFile, SubmissionFile

        child = self.child()
        sec = services.section_of(child)
        hw_id = self._int("homework")
        f = HomeworkFile.objects.filter(homework_id=hw_id, homework__section=sec, pk=self._int("file")).first() if sec else None
        if f is None:  # the child's own submitted file
            f = SubmissionFile.objects.filter(submission__homework_id=hw_id, submission__student=child, pk=self._int("file")).first()
        if f is None:
            raise NotFound()
        return download(f.file, f.original_name, f.content_type)

    @extend_schema(request={"multipart/form-data": OpenApiTypes.OBJECT}, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        from apps.learning import services as learning
        from apps.learning.models import Homework

        child = self.child()
        self.own(child)
        hw = Homework.objects.filter(pk=self._int("homework", request.data), section=services.section_of(child)).first()
        if hw is None:
            raise NotFound()
        files = request.FILES.getlist("files")
        if len(files) > 5:
            raise ValidationError({"files": "Attach at most 5 files."})
        for f in files:
            try:
                check_upload(f, allowed=LEARNING, max_mb=10)
            except serializers.ValidationError as exc:
                raise ValidationError({"files": exc.detail}) from exc
        learning.submit(homework=hw, student=child, text=str(request.data.get("text", ""))[:5000], files=files)
        return Response(next(h for h in services.homework(child) if h["id"] == hw.pk), status=status.HTTP_201_CREATED)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def materials(self, request, pk=None):
        return Response([{"id": m.pk, "subject": m.subject.name, "chapter": m.chapter, "title": m.title, "description": m.description,
                          "kind": m.kind, "link": m.link, "file": m.original_name if m.file else None}
                         for m in services.materials(self.child())])

    @extend_schema(parameters=[OpenApiParameter("material", int)], responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="material-file")
    def material_file(self, request, pk=None):
        m = services.materials(self.child()).filter(pk=self._int("material")).first()
        if m is None or not m.file:
            raise NotFound()
        return download(m.file, m.original_name, m.content_type)

    # -- online classes and tests -----------------------------------------
    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def classes(self, request, pk=None):
        from apps.learning.models import JoinRecord, OnlineClass

        child = self.child()
        sec = services.section_of(child)
        now = timezone.now()
        qs = [] if sec is None else OnlineClass.objects.filter(section=sec, ends_at__gte=now - timedelta(days=7)).select_related("subject").order_by("starts_at")
        joined = set(JoinRecord.objects.filter(student=child).values_list("online_class_id", flat=True))
        return Response([{"id": c.pk, "title": c.title, "subject": c.subject.name, "starts_at": c.starts_at, "ends_at": c.ends_at,
                          "state": "ended" if now > c.ends_at else ("open" if now >= c.starts_at - timedelta(minutes=15) else "later"),
                          "joined": c.pk in joined} for c in qs])

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def join(self, request, pk=None):
        from apps.learning import services as learning
        from apps.learning.models import OnlineClass

        child = self.child()
        self.own(child)
        c = OnlineClass.objects.filter(pk=self._int("online_class", request.data), section=services.section_of(child)).first()
        if c is None:
            raise NotFound()
        return Response({"link": learning.join(online_class=c, student=child)})

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def tests(self, request, pk=None):
        from apps.learning import services as learning
        from apps.learning.models import Attempt, OnlineTest

        child = self.child()
        sec = services.section_of(child)
        qs = [] if sec is None else list(OnlineTest.objects.filter(section=sec, published=True).select_related("subject").order_by("-opens_at")[:50])
        for t in qs:
            learning.close_expired(t)
        mine = {a.test_id: a for a in Attempt.objects.filter(student=child, test__in=qs)}
        now = timezone.now()
        out = []
        for t in qs:
            a = mine.get(t.pk)
            out.append({"id": t.pk, "title": t.title, "subject": t.subject.name, "opens_at": t.opens_at, "closes_at": t.closes_at,
                        "time_limit_minutes": t.time_limit_minutes, "questions": t.questions.count(),
                        "state": ("submitted" if a and a.submitted_at else "in progress" if a else
                                  "closed" if now >= t.closes_at else "open" if now >= t.opens_at else "later"),
                        "attempt": a.pk if a else None, "score": a.score if a and a.submitted_at else None,
                        "max_score": a.max_score if a and a.submitted_at else None})
        return Response(out)

    def _attempt_payload(self, a):
        t = a.test
        qs = list(t.questions.all())
        done = a.submitted_at is not None
        return {"attempt": a.pk, "test": t.pk, "title": t.title, "instructions": t.instructions, "deadline": a.deadline,
                "submitted_at": a.submitted_at, "score": a.score if done else None, "max_score": a.max_score if done else None,
                "auto_submitted": a.auto_submitted, "answers": a.answers,
                "questions": [{"id": q.pk, "sequence": q.sequence, "text": q.text, "options": q.options, "marks": q.marks,
                               **({"correct": q.correct} if done and t.show_answers else {})} for q in qs]}

    def _my_attempt(self, child, data):
        from apps.learning.models import Attempt

        a = Attempt.objects.select_related("test").filter(pk=self._int("attempt", data), student=child).first()
        if a is None:
            raise NotFound()
        return a

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="start-test")
    def start_test(self, request, pk=None):
        from apps.learning import services as learning
        from apps.learning.models import OnlineTest

        child = self.child()
        self.own(child)
        t = OnlineTest.objects.filter(pk=self._int("test", request.data), section=services.section_of(child), published=True).first()
        if t is None:
            raise NotFound()
        return Response(self._attempt_payload(learning.start_attempt(test=t, student=child)))

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="save-answers")
    def save_answers(self, request, pk=None):
        from apps.core.exceptions import Conflict
        from apps.learning.services import GRACE

        child = self.child()
        self.own(child)
        a = self._my_attempt(child, request.data)
        if a.submitted_at or timezone.now() > a.deadline + GRACE:
            raise Conflict("Time is up for this test.")
        answers = request.data.get("answers") or {}
        if not isinstance(answers, dict):
            raise ValidationError({"answers": "Expected {question id: choice}."})
        valid = {str(q.pk): len(q.options) for q in a.test.questions.all()}
        a.answers = {str(k): int(v) for k, v in answers.items() if str(k) in valid and str(v).isdigit() and int(v) < valid[str(k)]}
        a.save(update_fields=["answers", "updated_at"])
        return Response({"saved": len(a.answers)})

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="finish-test")
    def finish_test(self, request, pk=None):
        from apps.learning import services as learning

        child = self.child()
        self.own(child)
        a = self._my_attempt(child, request.data)
        answers = request.data.get("answers")
        a = learning.submit_attempt(attempt=a, answers=answers if isinstance(answers, dict) else a.answers)
        return Response(self._attempt_payload(a))

    @extend_schema(parameters=[OpenApiParameter("attempt", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def attempt(self, request, pk=None):
        child = self.child()
        return Response(self._attempt_payload(self._my_attempt(child, request.query_params)))

    # -- hostel and transport ----------------------------------------------
    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def outpasses(self, request, pk=None):
        from apps.hostel.models import Outpass

        child = self.child()
        return Response({"boarder": services.is_boarder(child),
                         "rows": [{"id": o.pk, "from_date": o.from_date, "to_date": o.to_date, "return_by": o.return_by,
                                   "destination": o.destination, "reason": o.reason, "status": o.status,
                                   "status_name": o.get_status_display(), "decision_note": o.decision_note,
                                   "requested_by": o.requested_by} for o in Outpass.objects.filter(student=child)[:50]]})

    @extend_schema(request=OutpassAskSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def outpass(self, request, pk=None):
        from apps.core.exceptions import Conflict
        from apps.hostel.gate import request_outpass
        from apps.hostel.models import Outpass

        child = self.child()
        if not services.is_boarder(child):
            raise Conflict("Outpasses are for hostel students.")
        s = OutpassAskSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        if v["from_date"] < self.today():
            raise Conflict("The leaving date has passed.")
        by = Outpass.RequestedBy.STUDENT if access.is_self(request, child) else Outpass.RequestedBy.PARENT
        op = request_outpass(student=child, from_date=v["from_date"], to_date=v["to_date"], reason=v["reason"],
                             destination=v.get("destination", ""), return_by=v.get("return_by"), requested_by=by)
        return Response({"id": op.pk, "status": op.status}, status=status.HTTP_201_CREATED)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def menu(self, request, pk=None):
        return Response(services.mess_menu(self.child()))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def transport(self, request, pk=None):
        return Response(services.transport(self.child(), self.today()))

    # -- notices, leave, change requests -----------------------------------
    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def notices(self, request, pk=None):
        qs, read = services.notices(self.child(), request.user)
        return Response([{"id": n.pk, "title": n.title, "body": n.body, "sent_at": n.sent_at, "read": n.pk in read} for n in qs[:100]])

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="read-notice")
    def read_notice(self, request, pk=None):
        from apps.notify.models import NoticeRead

        child = self.child()
        qs, _ = services.notices(child, request.user)
        n = qs.filter(pk=self._int("notice", request.data)).first()
        if n is None:
            raise NotFound()
        NoticeRead.objects.get_or_create(notice=n, user=request.user, defaults={"student": child})
        return Response({"read": True})

    @extend_schema(responses=StudentLeaveSerializer(many=True))
    @action(detail=True, methods=["get"])
    def leaves(self, request, pk=None):
        child = self.child()
        return Response(StudentLeaveSerializer(StudentLeave.objects.filter(student=child)[:50], many=True).data)

    @extend_schema(request=LeaveAskSerializer, responses=StudentLeaveSerializer)
    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        child = self.child()
        s = LeaveAskSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        lv = services.apply_leave(child=child, by=who(request), **s.validated_data)
        return Response(StudentLeaveSerializer(lv).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=ChangeRequestSerializer(many=True))
    @action(detail=True, methods=["get"])
    def changes(self, request, pk=None):
        child = self.child()
        return Response(ChangeRequestSerializer(ChangeRequest.objects.filter(student=child)[:50], many=True).data)

    @extend_schema(request=ChangeAskSerializer, responses=ChangeRequestSerializer)
    @action(detail=True, methods=["post"])
    def change(self, request, pk=None):
        child = self.child()
        if access.is_self(request, child):
            raise PermissionDenied("Ask a parent to request this change.")
        s = ChangeAskSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        g = (access.guardian_rows(request, child) or [None])[0]
        cr = services.ask_change(child=child, guardian=g, by=who(request), **s.validated_data)
        return Response(ChangeRequestSerializer(cr).data, status=status.HTTP_201_CREATED)


# ------------------------------------------------------------------ office / teacher side
class StudentLeaveViewSet(BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Day-scholar leave applications; the class teacher (or Admin) decides."""

    queryset = StudentLeave.objects.none()
    serializer_class = StudentLeaveSerializer
    perm_resource = "attendance.leave"
    action_perms = {"decide": "attendance.leave.manage"}
    filterset_fields = ["status", "student"]

    def get_queryset(self):
        self.queryset = StudentLeave.objects.select_related("student").order_by("-from_date", "-pk")
        qs = super().get_queryset()
        if request_can(self.request, "attendance.record.any_section"):
            return qs
        from apps.people.models import Enrollment, staff_for_user

        me = staff_for_user(self.request.user)
        return qs.filter(student__enrollments__section__class_teacher=me, student__enrollments__status=Enrollment.Status.ACTIVE,
                         student__enrollments__academic_year__is_current=True).distinct() if me else qs.none()

    @extend_schema(request=DecideSerializer, responses=StudentLeaveSerializer)
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        s = DecideSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        lv = services.decide_leave(leave=self.get_object(), approve=s.validated_data["approve"], by=who(request),
                                   note=s.validated_data["note"])
        return Response(StudentLeaveSerializer(lv).data)


class ChangeRequestViewSet(BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ChangeRequest.objects.none()
    serializer_class = ChangeRequestSerializer
    perm_resource = "office.change_request"
    action_perms = {"decide": "office.change_request.manage"}
    filterset_fields = ["status", "field", "student"]

    def get_queryset(self):
        self.queryset = ChangeRequest.objects.select_related("student", "guardian").order_by("-created_at")
        return super().get_queryset()

    @extend_schema(request=DecideSerializer, responses=ChangeRequestSerializer)
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        s = DecideSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cr = services.decide_change(request=self.get_object(), approve=s.validated_data["approve"], by=who(request),
                                    note=s.validated_data["note"])
        return Response(ChangeRequestSerializer(cr).data)


class StudentLoginViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Portal logins for students (the institution chooses which classes get one)."""

    queryset = Student.objects.none()
    serializer_class = StudentLoginSerializer
    perm_resource = "office.student_login"
    search_fields = ["full_name", "admission_no"]

    def get_queryset(self):
        self.queryset = Student.objects.filter(user__isnull=False).select_related("user").order_by("full_name")
        return super().get_queryset()

    @extend_schema(request=StudentLoginCreateSerializer, responses=StudentLoginSerializer)
    def create(self, request):
        s = StudentLoginCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        student = Student.objects.filter(pk=s.validated_data["student"], branch_id__in=resolve_scope(request).branch_ids).first()
        if student is None:
            raise ValidationError({"student": "Not found."})
        services.create_student_login(student=student, email=s.validated_data["email"], password=s.validated_data["password"],
                                      by=who(request))
        student.refresh_from_db()
        return Response(StudentLoginSerializer(student).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        services.remove_student_login(student=self.get_object(), by=who(request))
        return Response(status=status.HTTP_204_NO_CONTENT)
