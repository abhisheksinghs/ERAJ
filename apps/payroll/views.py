from rest_framework import mixins, viewsets
from rest_framework.response import Response

from apps.org.mixins import BranchScopedViewSetMixin
from apps.payroll import services
from apps.payroll.models import Payslip
from apps.payroll.serializers import GeneratePayslipSerializer, PayslipSerializer


class PayslipViewSet(
    BranchScopedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Payslip.objects.select_related("staff").all()
    serializer_class = PayslipSerializer
    perm_resource = "payroll.payslip"
    filterset_fields = ["staff", "period"]
    ordering_fields = ["period", "created_at"]

    def create(self, request, *args, **kwargs):
        data = GeneratePayslipSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        slip = services.generate_payslip(**data.validated_data)
        return Response(PayslipSerializer(slip).data, status=201)
