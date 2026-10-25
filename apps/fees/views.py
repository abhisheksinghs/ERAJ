from datetime import date

from django.db.models import Count, Prefetch, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.fees import services, tally
from apps.fees.models import Charge, Concession, FeeHead, FeePlan, FeeSettings, Receipt, ReceiptLine, Refund
from apps.fees.pdf import receipt_pdf
from apps.fees.selectors import charges_with_balance, students_with_dues
from apps.fees.serializers import (
    AdjustmentSerializer,
    CancelSerializer,
    ChargeSerializer,
    CollectSerializer,
    ConcessionSerializer,
    FeeHeadSerializer,
    FeePlanSerializer,
    FeeSettingsSerializer,
    ReceiptSerializer,
    RefundInSerializer,
    RefundSerializer,
    StudentAccountSerializer,
)
from apps.org.mixins import BranchScopedViewSetMixin
from apps.org.scope import resolve_scope
from apps.people.models import Enrollment, Student, StudentGuardian


def _who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


def _date_param(request, name: str, default: date) -> date:
    raw = request.query_params.get(name)
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({name: "Use YYYY-MM-DD."}) from exc


class FeeSettingsViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = FeeSettingsSerializer
    perm_resource = "fees.settings"
    queryset = FeeSettings.objects.all()

    def list(self, request, *args, **kwargs):
        # Ensure the active branch has a settings row before listing.
        scope = resolve_scope(request)
        if scope.active is not None:
            services.settings_for(scope.active)
        return super().list(request, *args, **kwargs)


class FeeHeadViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = FeeHead.objects.all()
    serializer_class = FeeHeadSerializer
    perm_resource = "fees.head"
    filterset_fields = ["kind", "is_active"]
    search_fields = ["name", "code"]


class FeePlanViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = FeePlan.objects.select_related("head", "program").prefetch_related("instalments")
    serializer_class = FeePlanSerializer
    perm_resource = "fees.plan"
    action_perms = {"apply": "fees.plan.manage"}
    filterset_fields = ["academic_year", "program", "head"]
    search_fields = ["name"]

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        """Bill every student currently enrolled in the plan's class/course."""
        return Response({"charges_created": services.apply_plan(self.get_object())})


class ChargeViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ChargeSerializer
    perm_resource = "fees.charge"
    action_perms = {"adjust": "fees.charge.manage"}
    filterset_fields = ["student", "head", "source_type", "academic_year"]
    search_fields = ["student__full_name", "student__admission_no", "description"]
    ordering_fields = ["due_date", "amount", "created_at"]

    def get_queryset(self):
        self.queryset = charges_with_balance(Charge.objects.select_related("student", "head"))
        qs = super().get_queryset()
        status = self.request.query_params.get("status")
        today = timezone.localdate()
        if status == "outstanding":
            qs = qs.filter(outstanding__gt=0)
        elif status == "overdue":
            qs = qs.filter(outstanding__gt=0, due_date__lt=today)
        elif status == "paid":
            qs = qs.filter(outstanding__lte=0)
        return qs

    @action(detail=False, methods=["post"])
    def adjust(self, request):
        data = AdjustmentSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        charge = services.add_adjustment(**data.validated_data)
        return Response(ChargeSerializer(charges_with_balance(Charge.objects.filter(pk=charge.pk)).get()).data, status=201)


class ConcessionViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                        mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Concession.objects.select_related("student", "head")
    serializer_class = ConcessionSerializer
    perm_resource = "fees.concession"
    action_perms = {"approve": "fees.concession.approve", "reject": "fees.concession.approve"}
    filterset_fields = ["status", "reason", "head", "student", "academic_year"]
    search_fields = ["student__full_name", "student__admission_no"]

    def perform_create(self, serializer):
        serializer.save(branch=self.active_branch(), requested_by=_who(self.request))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        c = services.decide_concession(concession=self.get_object(), approve=True, by=_who(request))
        return Response(ConcessionSerializer(c).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        c = services.decide_concession(concession=self.get_object(), approve=False, by=_who(request))
        return Response(ConcessionSerializer(c).data)


class ReceiptViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                     mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Receipt.objects.select_related("student").prefetch_related(
        Prefetch("lines", queryset=ReceiptLine.objects.select_related("charge", "charge__head"))
    )
    serializer_class = ReceiptSerializer
    perm_resource = "fees.receipt"
    action_perms = {"cancel": "fees.receipt.cancel"}
    filterset_fields = ["student", "mode", "date"]
    search_fields = ["number", "student__full_name", "student__admission_no", "reference"]
    ordering_fields = ["date", "sequence", "amount"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("from"):
            qs = qs.filter(date__gte=p["from"])
        if p.get("to"):
            qs = qs.filter(date__lte=p["to"])
        if p.get("cancelled") in ("true", "false"):
            qs = qs.filter(cancelled_at__isnull=p["cancelled"] == "false")
        return qs

    def create(self, request, *args, **kwargs):
        """Collect a payment at the counter."""
        data = CollectSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        v = data.validated_data
        lines = [services.LineIn(charge=l["charge"], amount=l["amount"]) for l in v.get("lines") or []] or None
        receipt = services.collect(
            student=v["student"], mode=v["mode"], reference=v["reference"], on=v.get("date"), note=v["note"],
            lines=lines, amount=v.get("amount"), received_by=_who(request),
        )
        return Response(ReceiptSerializer(self.get_queryset().get(pk=receipt.pk)).data, status=201)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        data = CancelSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.cancel_receipt(receipt=self.get_object(), by=_who(request), reason=data.validated_data["reason"])
        return Response(ReceiptSerializer(self.get_queryset().get(pk=pk)).data)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        receipt = self.get_object()
        duplicate = receipt.print_count > 0
        body = receipt_pdf(receipt, duplicate=duplicate)
        Receipt.objects.filter(pk=receipt.pk).update(print_count=receipt.print_count + 1)
        resp = HttpResponse(body, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{receipt.number.replace("/", "-")}.pdf"'
        return resp


class RefundViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                    mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Refund.objects.select_related("student")
    serializer_class = RefundSerializer
    perm_resource = "fees.refund"
    filterset_fields = ["student", "mode"]

    def create(self, request, *args, **kwargs):
        data = RefundInSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        v = data.validated_data
        obj = services.refund(
            student=v["student"], lines=[services.LineIn(charge=l["charge"], amount=l["amount"]) for l in v["lines"]],
            mode=v["mode"], reason=v["reason"], reference=v["reference"], on=v.get("date"), by=_who(request),
        )
        return Response(RefundSerializer(obj).data, status=201)


class StudentAccountViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                            viewsets.GenericViewSet):
    """Dues per student. `?overdue=true` is the defaulters list; filter by
    `program` / `section`. Retrieve adds the full ledger."""

    serializer_class = StudentAccountSerializer
    perm_resource = "fees.account"
    search_fields = ["full_name", "admission_no", "guardian_links__guardian__phone"]
    ordering_fields = ["outstanding", "overdue", "full_name", "admission_no"]

    def get_queryset(self):
        base = Student.objects.filter(status=Student.Status.ACTIVE).prefetch_related(
            Prefetch("guardian_links", queryset=StudentGuardian.objects.select_related("guardian"))
        )
        self.queryset = students_with_dues(base, timezone.localdate())
        qs = super().get_queryset()
        p = self.request.query_params
        current = Q(enrollments__academic_year__is_current=True, enrollments__status=Enrollment.Status.ACTIVE)
        if p.get("program"):
            qs = qs.filter(current, enrollments__program_id=p["program"])
        if p.get("section"):
            qs = qs.filter(current, enrollments__section_id=p["section"])
        if p.get("overdue") == "true":
            qs = qs.filter(overdue__gt=0)
        if p.get("outstanding") == "true":
            qs = qs.filter(outstanding__gt=0)
        return qs.distinct().order_by("-overdue", "full_name") if not p.get("ordering") else qs.distinct()

    def retrieve(self, request, *args, **kwargs):
        student = self.get_object()
        charges = charges_with_balance(Charge.objects.filter(student=student).select_related("head"))
        receipts = Receipt.objects.filter(student=student).prefetch_related("lines__charge__head")
        return Response(
            {
                "account": StudentAccountSerializer(student).data,
                "charges": ChargeSerializer(charges, many=True).data,
                "receipts": ReceiptSerializer(receipts, many=True).data,
                "refunds": RefundSerializer(Refund.objects.filter(student=student), many=True).data,
            }
        )


@extend_schema_view(
    collection=extend_schema(responses=OpenApiTypes.OBJECT),
    outstanding=extend_schema(responses=OpenApiTypes.OBJECT),
    tally=extend_schema(responses={(200, "application/xml"): OpenApiTypes.BINARY}),
)
class FeeReportViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    """Read-only reports. Collections exclude cancelled receipts (listed
    separately so the day's cash tallies)."""

    perm_resource = "fees.report"
    queryset = Receipt.objects.all()

    @action(detail=False, methods=["get"])
    def collection(self, request):
        today = timezone.localdate()
        d_from, d_to = _date_param(request, "from", today), _date_param(request, "to", today)
        receipts = self.get_queryset().filter(date__range=(d_from, d_to))
        live = receipts.filter(cancelled_at__isnull=True)
        by_mode = list(live.values("mode").annotate(amount=Sum("amount"), count=Count("id")).order_by("mode"))
        by_head = list(
            ReceiptLine.objects.filter(receipt__in=live)
            .values("charge__head__name")
            .annotate(amount=Sum("amount"))
            .order_by("charge__head__name")
        )
        cancelled = list(receipts.filter(cancelled_at__isnull=False).values("number", "amount", "cancel_reason", "cancelled_by"))
        return Response(
            {
                "from": d_from,
                "to": d_to,
                "total": live.aggregate(t=Sum("amount"))["t"] or 0,
                "count": live.count(),
                "by_mode": by_mode,
                "by_head": [{"head": r["charge__head__name"], "amount": r["amount"]} for r in by_head],
                "cancelled": cancelled,
            }
        )

    @action(detail=False, methods=["get"])
    def outstanding(self, request):
        """Outstanding and overdue dues per class/course and section."""
        today = timezone.localdate()
        scope = resolve_scope(request)
        rows = (
            charges_with_balance(
                Charge.objects.filter(
                    branch_id__in=scope.branch_ids,
                    student__enrollments__academic_year__is_current=True,
                    student__enrollments__status=Enrollment.Status.ACTIVE,
                )
            )
            .values("student__enrollments__program__name", "student__enrollments__section__name")
            .annotate(
                total_outstanding=Sum("outstanding"),
                total_overdue=Sum("outstanding", filter=Q(due_date__lt=today)),
                students=Count("student", distinct=True, filter=Q(outstanding__gt=0)),
            )
            .order_by("student__enrollments__program__name", "student__enrollments__section__name")
        )
        return Response(
            [
                {
                    "program": r["student__enrollments__program__name"],
                    "section": r["student__enrollments__section__name"],
                    "outstanding": r["total_outstanding"] or 0,
                    "overdue": r["total_overdue"] or 0,
                    "students_with_dues": r["students"],
                }
                for r in rows
            ]
        )

    @action(detail=False, methods=["get"])
    def tally(self, request):
        scope = resolve_scope(request)
        if scope.active is None:
            raise ValidationError({"branch": "Choose one branch to export for Tally."})
        today = timezone.localdate()
        xml = tally.export_xml(
            branch=scope.active, date_from=_date_param(request, "from", today), date_to=_date_param(request, "to", today)
        )
        resp = HttpResponse(xml, content_type="application/xml")
        resp["Content-Disposition"] = f'attachment; filename="tally-{scope.active.code}-{today:%Y%m%d}.xml"'
        return resp
