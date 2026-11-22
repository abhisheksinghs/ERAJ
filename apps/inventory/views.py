from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.inventory import services
from apps.inventory.models import (
    DirectPurchase, GoodsReceipt, InventorySettings, IssueRecord, Item, PurchaseOrder, Requisition, StockMove, Store, Vendor,
)
from apps.inventory.serializers import (
    AdjustSerializer, CloseIssueSerializer, DirectPurchaseSerializer, GoodsReceiptSerializer, InventorySettingsSerializer,
    IssueRecordSerializer, StockIssueSerializer, ItemSerializer, StockNoteSerializer, PurchaseOrderSerializer, StockReasonSerializer,
    ReceiveSerializer, RequisitionSerializer, StockMoveSerializer, StoreSerializer, VendorSerializer,
)
from apps.org.mixins import BranchScopedViewSetMixin
from apps.org.scope import resolve_scope


def who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


def qdate(request, name, default) -> date:
    raw = request.query_params.get(name)
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({name: "Use YYYY-MM-DD."}) from exc


def _store(request):
    sid = request.query_params.get("store")
    if not sid:
        return None
    s = Store.objects.filter(pk=sid, branch_id__in=resolve_scope(request).branch_ids).first()
    if s is None:
        raise ValidationError({"store": "Not found."})
    return s


class StoreViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Store.objects.select_related("mess")
    serializer_class = StoreSerializer
    perm_resource = "inventory.store"


class VendorViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    perm_resource = "inventory.vendor"
    search_fields = ["name", "gstin", "phone"]


class ItemViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Item.objects.select_related("store")
    serializer_class = ItemSerializer
    perm_resource = "inventory.item"
    action_perms = {"issue": "inventory.issue.manage", "adjust": "inventory.stock.adjust"}
    filterset_fields = ["store", "kind", "category"]
    search_fields = ["name", "code", "category"]
    ordering_fields = ["name", "code", "quantity"]

    def perform_create(self, serializer):
        qty = serializer.validated_data.pop("opening_quantity", None)
        rate = serializer.validated_data.pop("opening_rate", None)
        item = serializer.save(branch=self.active_branch())
        if qty:
            services.opening_stock(item=item, quantity=qty, rate=rate or 0, by=who(self.request))

    def perform_update(self, serializer):
        serializer.validated_data.pop("opening_quantity", None)
        serializer.validated_data.pop("opening_rate", None)
        serializer.save()

    @extend_schema(request=StockIssueSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def issue(self, request):
        s = StockIssueSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        v = s.validated_data
        r = services.issue(item=v["item"], quantity=v["quantity"], staff=v.get("staff"), department=v.get("department"),
                           due_back=v.get("due_back"), note=v["note"], by=who(request))
        if isinstance(r, IssueRecord):
            return Response(IssueRecordSerializer(r, context={"request": request}).data, status=status.HTTP_201_CREATED)
        return Response(StockMoveSerializer(r, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=AdjustSerializer, responses=StockMoveSerializer)
    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        s = AdjustSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        m = services.adjust(item=self.get_object(), counted=s.validated_data["counted"], reason=s.validated_data["reason"],
                            by=who(request))
        return Response(StockMoveSerializer(m, context={"request": request}).data)

    @extend_schema(parameters=[OpenApiParameter("from", str), OpenApiParameter("to", str)], responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        return Response(services.ledger(self.get_object(), qdate(request, "from", None), qdate(request, "to", None)))


class StockMoveViewSet(BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = StockMove.objects.select_related("item", "staff", "department", "vendor")
    serializer_class = StockMoveSerializer
    perm_resource = "inventory.item"
    filterset_fields = ["item", "kind", "staff", "department"]


class IssueRecordViewSet(BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = IssueRecord.objects.select_related("item", "staff")
    serializer_class = IssueRecordSerializer
    perm_resource = "inventory.issue"
    action_perms = {"close": "inventory.issue.manage"}
    filterset_fields = ["status", "staff", "item"]
    search_fields = ["staff__full_name", "item__name"]

    @extend_schema(request=CloseIssueSerializer, responses=IssueRecordSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        s = CloseIssueSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        r = services.close_issue(issue=self.get_object(), outcome=s.validated_data["outcome"], note=s.validated_data["note"],
                                 by=who(request))
        return Response(IssueRecordSerializer(r, context={"request": request}).data)


class RequisitionViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                         mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Requisition.objects.select_related("department").prefetch_related("lines__item", "approvals")
    serializer_class = RequisitionSerializer
    perm_resource = "inventory.requisition"
    action_perms = {"submit": "inventory.requisition.manage", "approve": "inventory.requisition.approve",
                    "reject": "inventory.requisition.approve"}
    filterset_fields = ["status", "department"]

    def perform_create(self, serializer):
        v = serializer.validated_data
        serializer.instance = services.create_requisition(department=v["department"], lines=v["lines"],
                                                          purpose=v.get("purpose", ""), by=who(self.request))

    def _out(self, req, request):
        return Response(RequisitionSerializer(Requisition.objects.get(pk=req.pk), context={"request": request}).data)

    @extend_schema(request=None, responses=RequisitionSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._out(services.submit_requisition(requisition=self.get_object(), by=who(request)), request)

    @extend_schema(request=StockNoteSerializer, responses=RequisitionSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        s = StockNoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._out(services.approve_requisition(requisition=self.get_object(), user=request.user,
                                                      note=s.validated_data["note"]), request)

    @extend_schema(request=StockNoteSerializer, responses=RequisitionSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        s = StockNoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._out(services.reject_requisition(requisition=self.get_object(), by=who(request),
                                                     note=s.validated_data["note"]), request)


class PurchaseOrderViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                           mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = PurchaseOrder.objects.select_related("vendor").prefetch_related("lines__item")
    serializer_class = PurchaseOrderSerializer
    perm_resource = "inventory.order"
    action_perms = {"receive": "inventory.order.receive", "cancel": "inventory.order.manage"}
    filterset_fields = ["status", "vendor"]
    search_fields = ["number", "vendor__name"]

    def perform_create(self, serializer):
        v = serializer.validated_data
        serializer.instance = services.raise_order(vendor=v["vendor"], lines=v.get("lines") or [], requisition=v.get("requisition"),
                                                   terms=v.get("terms", ""), by=who(self.request))

    @extend_schema(request=ReceiveSerializer, responses=GoodsReceiptSerializer)
    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        s = ReceiveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        g = services.receive(order=self.get_object(), quantities=s.validated_data["lines"],
                             challan_no=s.validated_data["challan_no"], by=who(request))
        return Response(GoodsReceiptSerializer(g, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=StockReasonSerializer, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        s = StockReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        po = services.cancel_order(order=self.get_object(), reason=s.validated_data["reason"], by=who(request))
        return Response(PurchaseOrderSerializer(po, context={"request": request}).data)

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        from apps.inventory.pdf import po_pdf

        po = self.get_object()
        resp = HttpResponse(po_pdf(po), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="{po.number.replace("/", "-")}.pdf"'
        return resp


class GoodsReceiptViewSet(BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = GoodsReceipt.objects.select_related("order")
    serializer_class = GoodsReceiptSerializer
    perm_resource = "inventory.order"
    filterset_fields = ["order"]


class DirectPurchaseViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                            mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = DirectPurchase.objects.select_related("vendor").prefetch_related("lines__item")
    serializer_class = DirectPurchaseSerializer
    perm_resource = "inventory.purchase"
    filterset_fields = ["vendor"]

    def perform_create(self, serializer):
        v = serializer.validated_data
        serializer.instance = services.direct_purchase(vendor=v["vendor"], bill_no=v["bill_no"], bill_date=v["bill_date"],
                                                       lines=v["lines"], note=v.get("note", ""), by=who(self.request))


class InventorySettingsViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                               mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = InventorySettings.objects.all()
    serializer_class = InventorySettingsSerializer
    perm_resource = "inventory.settings"

    def list(self, request, *args, **kwargs):
        if resolve_scope(request).active is not None:
            services.settings_for(resolve_scope(request).active)
        return super().list(request, *args, **kwargs)


class InventoryReportViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    perm_resource = "inventory.report"
    queryset = Item.objects.none()

    def _range(self, request):
        today = timezone.localdate()
        return qdate(request, "from", today.replace(day=1)), qdate(request, "to", today)

    @extend_schema(parameters=[OpenApiParameter("store", int), OpenApiParameter("low", bool)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def stock(self, request):
        return Response(services.stock(branch=self.active_branch(), store=_store(request),
                                       low_only=request.query_params.get("low") in ("1", "true")))

    @extend_schema(parameters=[OpenApiParameter("from", str), OpenApiParameter("to", str), OpenApiParameter("store", int)],
                   responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def consumption(self, request):
        start, end = self._range(request)
        return Response(services.consumption(branch=self.active_branch(), start=start, end=end, store=_store(request)))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path="with-staff")
    def with_staff(self, request):
        return Response(services.with_staff(branch=self.active_branch()))

    @extend_schema(parameters=[OpenApiParameter("from", str), OpenApiParameter("to", str)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def vendors(self, request):
        start, end = self._range(request)
        return Response(services.purchases_by_vendor(branch=self.active_branch(), start=start, end=end))
