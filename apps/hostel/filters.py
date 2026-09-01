from django.db.models import Count, F, Q
from django_filters import rest_framework as filters

from apps.hostel.models import Allocation, Room


class RoomFilter(filters.FilterSet):
    has_space = filters.BooleanFilter(method="_has_space")

    class Meta:
        model = Room
        fields = ["room_type", "gender", "floor", "status"]

    def _has_space(self, queryset, name, value):
        annotated = queryset.annotate(
            _occupied=Count("allocations", filter=Q(allocations__check_out_date__isnull=True))
        )
        if not value:
            return annotated
        return annotated.filter(status=Room.Status.ACTIVE, _occupied__lt=F("capacity"))


class AllocationFilter(filters.FilterSet):
    active = filters.BooleanFilter(field_name="check_out_date", lookup_expr="isnull")

    class Meta:
        model = Allocation
        fields = ["resident", "room"]
