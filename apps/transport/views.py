from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.org.mixins import BranchScopedViewSetMixin
from apps.org.scope import resolve_scope
from apps.transport import services
from apps.transport.models import (
    FareSlab, Route, RouteStop, TransportAlert, TransportAssignment, TransportSettings, Vehicle, VehicleDocument,
)
from apps.transport.serializers import (
    ChangeSerializer, FareSlabSerializer, RouteSerializer, StopChoiceSerializer, StopFromSerializer,
    TransportAlertSerializer, TransportAssignmentSerializer, TransportSettingsSerializer, VehicleDocumentSerializer,
    VehicleSerializer,
)


def who(request) -> str:
    return getattr(request.user, "email", "") or "unknown"


def qdate(request, name="date", default=None) -> date:
    raw = request.query_params.get(name)
    if not raw:
        return default or timezone.localdate()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({name: "Use YYYY-MM-DD."}) from exc


def scoped(request, model, pk):
    obj = model.objects.filter(pk=pk, branch_id__in=resolve_scope(request).branch_ids).first()
    if obj is None:
        raise ValidationError({model.__name__.lower(): "Not found."})
    return obj


class RouteViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Route.objects.prefetch_related("stops")
    serializer_class = RouteSerializer
    perm_resource = "transport.route"
    search_fields = ["code", "name"]


class StopViewSet(BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Stops for pick lists (route-wise label)."""

    queryset = RouteStop.objects.select_related("route")
    serializer_class = StopChoiceSerializer
    perm_resource = "transport.route"
    filterset_fields = ["route"]
    search_fields = ["name", "route__code"]


class FareSlabViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = FareSlab.objects.all()
    serializer_class = FareSlabSerializer
    perm_resource = "transport.fare"


class VehicleViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Vehicle.objects.select_related("route")
    serializer_class = VehicleSerializer
    perm_resource = "transport.vehicle"
    action_perms = {"rotate_key": "transport.vehicle.manage"}
    filterset_fields = ["route", "kind", "is_active"]
    search_fields = ["registration_no", "driver_name"]

    @extend_schema(request=None, responses=VehicleSerializer)
    @action(detail=True, methods=["post"], url_path="rotate-key")
    def rotate_key(self, request, pk=None):
        from apps.core.audit import record
        from apps.transport.models import _key

        v = self.get_object()
        v.gps_key = _key()
        v.save(update_fields=["gps_key", "updated_at"])
        record("transport.gps_key_rotated", actor=who(request), vehicle=v.pk)
        return Response({"gps_key": v.gps_key})

    @extend_schema(parameters=[OpenApiParameter("date", str)], responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def trip(self, request, pk=None):
        return Response(services.trip(self.get_object(), qdate(request)))


class VehicleDocumentViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = VehicleDocument.objects.select_related("vehicle")
    serializer_class = VehicleDocumentSerializer
    perm_resource = "transport.document"
    filterset_fields = ["vehicle", "kind"]


class TransportAssignmentViewSet(BranchScopedViewSetMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                                 mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = TransportAssignment.objects.select_related("student", "staff", "route", "stop", "vehicle")
    serializer_class = TransportAssignmentSerializer
    perm_resource = "transport.assignment"
    action_perms = {"stop": "transport.assignment.manage", "change": "transport.assignment.manage"}
    filterset_fields = ["route", "stop", "vehicle", "student", "staff"]
    search_fields = ["student__full_name", "student__admission_no", "staff__full_name", "vehicle__registration_no"]

    def get_queryset(self):
        qs = super().get_queryset()
        riding = self.request.query_params.get("riding")
        if self.action == "list" and riding in ("true", "1", None):
            from django.db.models import Q

            qs = qs.filter(Q(end_date__isnull=True) | Q(end_date__gte=timezone.localdate()))
        return qs

    def perform_create(self, serializer):
        v = serializer.validated_data
        if v["stop"].route_id != v["vehicle"].route_id:
            raise ValidationError({"vehicle": "That vehicle doesn't run on the stop's route."})
        serializer.instance = services.assign(stop=v["stop"], vehicle=v["vehicle"], start=v["start_date"],
                                              student=v.get("student"), staff=v.get("staff"), note=v.get("note", ""),
                                              by=who(self.request))

    @extend_schema(request=StopFromSerializer, responses=TransportAssignmentSerializer)
    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        s = StopFromSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        a = services.stop(assignment=self.get_object(), from_date=s.validated_data["from_date"], by=who(request))
        if a.pk is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(TransportAssignmentSerializer(a, context={"request": request}).data)

    @extend_schema(request=ChangeSerializer, responses=TransportAssignmentSerializer)
    @action(detail=True, methods=["post"])
    def change(self, request, pk=None):
        s = ChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        a = services.change(assignment=self.get_object(), stop_to=scoped(request, RouteStop, v["stop"]),
                            vehicle=scoped(request, Vehicle, v["vehicle"]), from_date=v["from_date"], by=who(request))
        return Response(TransportAssignmentSerializer(a, context={"request": request}).data, status=status.HTTP_201_CREATED)


class TransportSettingsViewSet(BranchScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                               mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = TransportSettings.objects.all()
    serializer_class = TransportSettingsSerializer
    perm_resource = "transport.settings"

    def list(self, request, *args, **kwargs):
        if resolve_scope(request).active is not None:
            services.settings_for(resolve_scope(request).active)
        return super().list(request, *args, **kwargs)


class TransportAlertViewSet(BranchScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = TransportAlert.objects.select_related("vehicle", "stop")
    serializer_class = TransportAlertSerializer
    perm_resource = "transport.alert"
    filterset_fields = ["vehicle", "kind"]


class TransportReportViewSet(BranchScopedViewSetMixin, viewsets.GenericViewSet):
    perm_resource = "transport.report"
    queryset = TransportAssignment.objects.none()

    @extend_schema(parameters=[OpenApiParameter("route", int), OpenApiParameter("date", str), OpenApiParameter("pdf", bool)],
                   responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def riders(self, request):
        branch = self.active_branch()
        route = scoped(request, Route, request.query_params["route"]) if request.query_params.get("route") else None
        on = qdate(request)
        rows = services.riders(branch=branch, route=route, on=on)
        if not request.query_params.get("pdf"):
            return Response(rows)
        from apps.transport.pdf import riders_pdf

        resp = HttpResponse(riders_pdf(rows, branch=branch, route=route, on=on), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="riders-{route.code if route else "all"}-{on}.pdf"'
        return resp

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def occupancy(self, request):
        return Response(services.occupancy_report(branch=self.active_branch()))

    @extend_schema(parameters=[OpenApiParameter("days", int)], responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def expiring(self, request):
        days = int(request.query_params.get("days") or 30)
        return Response(services.expiring_documents(branch=self.active_branch(), within_days=max(0, min(days, 365))))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def live(self, request):
        return Response(services.live(self.active_branch()))
