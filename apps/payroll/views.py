from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.org.mixins import BranchScopedViewSetMixin
from apps.payroll import exports, services
from apps.payroll.models import (
    DARate, Loan, OneTimePayment, PayComponent, PayLevel, PayrollRun, PayRuleSet, Payslip, SalaryStructure, StatutorySettings,
)
from apps.payroll.serializers import (
    DARateSerializer, LoanSerializer, OneTimePaymentSerializer, PayComponentSerializer, PayLevelSerializer,
    PayrollRunSerializer, PayRuleSetSerializer, PayslipSerializer, ReasonSerializer, ReviseDASerializer,
    SalaryStructureSerializer, StatutorySettingsSerializer,
)
from apps.people.models import Staff, staff_for_user


def who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


def _fy(request) -> int:
    raw = request.query_params.get("fy")
    return int(raw) if raw and raw.isdigit() else exports.current_fy(timezone.localdate())


def _pdf(content: bytes, name: str) -> HttpResponse:
    resp = HttpResponse(content, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{name}"'
    return resp


class PayRuleSetViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = PayRuleSet.objects.all()
    serializer_class = PayRuleSetSerializer
    perm_resource = "payroll.ruleset"
    action_perms = {"revise_da": "payroll.da.manage"}

    @extend_schema(request=ReviseDASerializer, responses=DARateSerializer)
    @action(detail=True, methods=["post"], url_path="revise-da")
    def revise_da(self, request, pk=None):
        s = ReviseDASerializer(data=request.data)
        s.is_valid(raise_exception=True)
        rate = services.revise_da(rule_set=self.get_object(), percent=s.validated_data["percent"],
                                  effective_from=s.validated_data["effective_from"], note=s.validated_data["note"],
                                  by=who(request))
        return Response(DARateSerializer(rate, context={"request": request}).data, status=status.HTTP_201_CREATED)


class PayLevelViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = PayLevel.objects.select_related("rule_set").prefetch_related("cells")
    serializer_class = PayLevelSerializer
    perm_resource = "payroll.ruleset"
    filterset_fields = ["rule_set"]


class DARateViewSet(BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = DARate.objects.select_related("rule_set")
    serializer_class = DARateSerializer
    perm_resource = "payroll.ruleset"
    filterset_fields = ["rule_set"]


class PayComponentViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = PayComponent.objects.select_related("rule_set")
    serializer_class = PayComponentSerializer
    perm_resource = "payroll.ruleset"
    filterset_fields = ["rule_set", "kind"]


class StatutorySettingsViewSet(BranchScopedViewSetMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                               viewsets.GenericViewSet):
    queryset = StatutorySettings.objects.all()
    serializer_class = StatutorySettingsSerializer
    perm_resource = "payroll.settings"

    @extend_schema(responses=StatutorySettingsSerializer)
    @action(detail=False, methods=["get"])
    def current(self, request):
        return Response(self.get_serializer(services.statutory_for(self.active_branch())).data)

    def perform_update(self, serializer):
        from apps.core.audit import record

        obj = serializer.save()
        record("payroll.settings.changed", actor=who(self.request), branch=obj.branch_id, fields=sorted(serializer.validated_data))


class SalaryStructureViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = SalaryStructure.objects.select_related("staff", "rule_set", "level").prefetch_related("overrides__component")
    serializer_class = SalaryStructureSerializer
    perm_resource = "payroll.structure"
    filterset_fields = ["rule_set", "level", "pf", "nps", "esi", "is_active"]
    search_fields = ["staff__full_name", "staff__employee_code"]

    def perform_create(self, serializer):
        from apps.core.audit import record

        s = serializer.save(branch=self.active_branch())
        record("payroll.structure.created", actor=who(self.request), staff=s.staff_id, rule_set=s.rule_set.code)

    def perform_update(self, serializer):
        from apps.core.audit import record

        s = serializer.save()
        record("payroll.structure.changed", actor=who(self.request), staff=s.staff_id, fields=sorted(serializer.validated_data))


class LoanViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                  mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Loan.objects.select_related("staff")
    serializer_class = LoanSerializer
    perm_resource = "payroll.loan"
    filterset_fields = ["staff", "status", "kind"]

    def perform_create(self, serializer):
        v = serializer.validated_data
        serializer.instance = services.create_loan(staff=v["staff"], kind=v.get("kind", Loan.Kind.ADVANCE), amount=v["amount"],
                                                   monthly_recovery=v["monthly_recovery"], start_month=v["start_month"],
                                                   note=v.get("note", ""), by=who(self.request))


class OneTimePaymentViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = OneTimePayment.objects.select_related("staff")
    serializer_class = OneTimePaymentSerializer
    perm_resource = "payroll.onetime"
    filterset_fields = ["staff", "month", "kind"]

    def _guard(self, month):
        services.guard_month_open(branch=self.active_branch(), month=month)

    def perform_create(self, serializer):
        self._guard(serializer.validated_data["month"])
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._guard(serializer.instance.month)
        self._guard(serializer.validated_data.get("month", serializer.instance.month))
        serializer.save()

    def perform_destroy(self, instance):
        self._guard(instance.month)
        instance.delete()


class PayrollRunViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                        mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Monthly run: create (draft, computed) → recompute → submit → lock; Admin reverses with a reason."""

    queryset = PayrollRun.objects.all()
    serializer_class = PayrollRunSerializer
    perm_resource = "payroll.run"
    action_perms = {"recompute": "payroll.run.manage", "submit": "payroll.run.manage",
                    "back_to_draft": "payroll.run.manage", "lock": "payroll.run.lock", "reverse": "payroll.run.reverse"}
    filterset_fields = ["status"]

    def perform_create(self, serializer):
        serializer.instance = services.create_run(branch=self.active_branch(), month=serializer.validated_data["month"],
                                                  by=who(self.request))

    def _verb(self, request, fn, **kw):
        run = fn(run=self.get_object(), by=who(request), **kw)
        return Response(PayrollRunSerializer(run, context={"request": request}).data)

    @extend_schema(request=None, responses=PayrollRunSerializer)
    @action(detail=True, methods=["post"])
    def recompute(self, request, pk=None):
        return self._verb(request, services.recompute)

    @extend_schema(request=None, responses=PayrollRunSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._verb(request, services.submit)

    @extend_schema(request=None, responses=PayrollRunSerializer)
    @action(detail=True, methods=["post"], url_path="back-to-draft")
    def back_to_draft(self, request, pk=None):
        return self._verb(request, services.back_to_draft)

    @extend_schema(request=None, responses=PayrollRunSerializer)
    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        return self._verb(request, services.lock)

    @extend_schema(request=ReasonSerializer, responses=PayrollRunSerializer)
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._verb(request, services.reverse, reason=s.validated_data["reason"])

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"], url_path="bank-sheet")
    def bank_sheet(self, request, pk=None):
        return Response(exports.bank_sheet(self.get_object()))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def register(self, request, pk=None):
        return Response(exports.salary_register(self.get_object()))

    @extend_schema(responses={(200, "text/plain"): OpenApiTypes.STR})
    @action(detail=True, methods=["get"])
    def ecr(self, request, pk=None):
        run = self.get_object()
        resp = HttpResponse(exports.ecr_text(run), content_type="text/plain; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="ECR-{run.month:%Y-%m}.txt"'
        return resp

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def esic(self, request, pk=None):
        return Response(exports.esic_sheet(self.get_object()))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"], url_path="pt-register")
    def pt_register(self, request, pk=None):
        return Response(exports.pt_register(self.get_object()))

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def payslips(self, request, pk=None):
        from apps.payroll.pdf import payslips_pdf

        run = self.get_object()
        slips = run.payslips.select_related("staff__department", "staff__hr_profile").prefetch_related("lines").order_by("staff__employee_code")
        return _pdf(payslips_pdf(list(slips), branch=run.branch), f"payslips-{run.month:%Y-%m}.pdf")


class PayslipViewSet(BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Payslip.objects.select_related("staff", "run").prefetch_related("lines")
    serializer_class = PayslipSerializer
    perm_resource = "payroll.payslip"
    filterset_fields = ["run", "staff", "month"]
    search_fields = ["staff__full_name", "staff__employee_code"]

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        from apps.payroll.pdf import payslips_pdf

        slip = self.get_object()
        return _pdf(payslips_pdf([slip], branch=slip.branch), f"payslip-{slip.staff.employee_code}-{slip.month:%Y-%m}.pdf")


class PayrollReportViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    perm_resource = "payroll.report"
    queryset = Payslip.objects.none()

    @extend_schema(parameters=[OpenApiParameter("fy", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def statutory(self, request):
        return Response(exports.statutory_summary(self.active_branch(), _fy(request)))

    @extend_schema(parameters=[OpenApiParameter("fy", int), OpenApiParameter("quarter", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path="tds-24q")
    def tds_24q(self, request):
        q = request.query_params.get("quarter", "")
        if not q.isdigit():
            raise ValidationError({"quarter": "1 to 4."})
        return Response(exports.tds_24q(self.active_branch(), _fy(request), int(q)))

    @extend_schema(parameters=[OpenApiParameter("fy", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def form16(self, request):
        return Response(exports.form16(self.active_branch(), _fy(request)))

    @extend_schema(parameters=[OpenApiParameter("fy", int), OpenApiParameter("staff", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def ytd(self, request):
        branch = self.active_branch()
        staff = None
        if request.query_params.get("staff"):
            staff = Staff.objects.filter(pk=request.query_params["staff"], branch=branch).first()
            if staff is None:
                raise ValidationError({"staff": "Not found."})
        return Response(exports.ytd(branch, _fy(request), staff))


class MyPayslipViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    """A staff login's own payslips (locked months only)."""

    perm_resource = "payroll.self"
    queryset = Payslip.objects.none()

    def _mine(self, request):
        me = staff_for_user(request.user)
        if me is None:
            raise NotFound("Your login isn't linked to a staff record.")
        return Payslip.objects.filter(staff=me, run__status=PayrollRun.Status.LOCKED).select_related("staff", "run").prefetch_related("lines")

    @extend_schema(responses=PayslipSerializer(many=True))
    @action(detail=False, methods=["get"])
    def payslips(self, request):
        return Response(PayslipSerializer(self._mine(request).order_by("-month"), many=True, context={"request": request}).data)

    @extend_schema(parameters=[OpenApiParameter("month", str)], responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=False, methods=["get"])
    def pdf(self, request):
        from apps.payroll.pdf import payslips_pdf

        raw = request.query_params.get("month", "")
        try:
            month = date.fromisoformat(f"{raw[:7]}-01")
        except ValueError as exc:
            raise ValidationError({"month": "Use YYYY-MM."}) from exc
        slip = self._mine(request).filter(month=month).first()
        if slip is None:
            raise NotFound("No payslip for that month.")
        return _pdf(payslips_pdf([slip], branch=slip.branch), f"payslip-{month:%Y-%m}.pdf")
