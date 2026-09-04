from rest_framework import mixins, viewsets
from rest_framework.response import Response

from apps.accounts.permissions import RolePermission
from apps.payroll import services
from apps.payroll.models import Payslip
from apps.payroll.serializers import GeneratePayslipSerializer, PayslipSerializer


class PayslipViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = Payslip.objects.select_related("employee").all()
    serializer_class = PayslipSerializer
    permission_classes = [RolePermission]
    filterset_fields = ["employee", "period"]
    ordering_fields = ["period", "created_at"]

    def create(self, request, *args, **kwargs):
        data = GeneratePayslipSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        slip = services.generate_payslip(**data.validated_data)
        return Response(PayslipSerializer(slip).data, status=201)
