from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import RolePermission
from apps.inventory import services
from apps.inventory.models import Item, IssueRecord
from apps.inventory.serializers import IssueCreateSerializer, IssueRecordSerializer, ItemSerializer


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    permission_classes = [RolePermission]
    filterset_fields = ["category"]
    search_fields = ["name", "sku"]
    ordering_fields = ["name", "quantity_available", "created_at"]


class IssueRecordViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = IssueRecord.objects.select_related("item").all()
    serializer_class = IssueRecordSerializer
    permission_classes = [RolePermission]
    filterset_fields = ["item"]
    ordering_fields = ["created_at"]

    def create(self, request, *args, **kwargs):
        data = IssueCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        issue = services.issue_item(**data.validated_data)
        return Response(IssueRecordSerializer(issue).data, status=201)

    @action(detail=True, methods=["post"], url_path="return")
    def return_item(self, request, pk=None):
        return Response(IssueRecordSerializer(services.return_item(issue=self.get_object())).data)
