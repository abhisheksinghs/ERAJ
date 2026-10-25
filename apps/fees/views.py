from decimal import Decimal

from django.db.models import Count, Sum
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.org.mixins import BranchScopedViewSetMixin
from apps.fees import services
from apps.fees.models import FeeStructure, Payment
from apps.fees.serializers import (
    CollectionsSerializer,
    FeeStructureSerializer,
    PaymentSerializer,
    RecordPaymentSerializer,
)


class FeeStructureViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = FeeStructure.objects.all()
    serializer_class = FeeStructureSerializer
    perm_resource = "fees.structure"
    search_fields = ["name", "term"]
    ordering_fields = ["due_date", "amount", "created_at"]

    @action(detail=True, methods=["get"])
    def collections(self, request, pk=None):
        fee_structure = self.get_object()
        agg = fee_structure.payments.aggregate(total=Sum("amount"), n=Count("id"))
        return Response(
            CollectionsSerializer(
                {
                    "fee_structure": fee_structure.pk,
                    "total_collected": agg["total"] or Decimal("0.00"),
                    "payment_count": agg["n"] or 0,
                }
            ).data
        )


class PaymentViewSet(
    BranchScopedViewSetMixin,
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = Payment.objects.select_related("fee_structure").all()
    serializer_class = PaymentSerializer
    perm_resource = "fees.payment"
    filterset_fields = ["fee_structure"]
    search_fields = ["payer_name", "payer_reference", "receipt_no"]
    ordering_fields = ["created_at", "amount"]

    def create(self, request, *args, **kwargs):
        data = RecordPaymentSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        payment = services.record_payment(**data.validated_data)
        return Response(PaymentSerializer(payment).data, status=201)
