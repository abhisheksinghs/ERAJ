from django.db.models import F, Q
from django_filters import rest_framework as filters

from apps.hostel.models import Allocation, MessMember, Outpass, Room, Visit


class RoomFilter(filters.FilterSet):
    has_space = filters.BooleanFilter(method="_has_space")

    class Meta:
        model = Room
        fields = ["block", "room_type", "gender", "floor", "status"]

    def _has_space(self, queryset, name, value):
        # needs the occupied_count / open_repairs annotations from RoomViewSet
        free = Q(status=Room.Status.ACTIVE, occupied_count__lt=F("capacity"), open_repairs=0)
        return queryset.filter(free) if value else queryset.exclude(free)


class AllocationFilter(filters.FilterSet):
    active = filters.BooleanFilter(field_name="check_out_date", lookup_expr="isnull")
    block = filters.NumberFilter(field_name="room__block")

    class Meta:
        model = Allocation
        fields = ["student", "room"]


class MessMemberFilter(filters.FilterSet):
    active = filters.BooleanFilter(field_name="end_date", lookup_expr="isnull")
    kind = filters.ChoiceFilter(choices=[("student", "Student"), ("staff", "Staff")], method="_kind")

    class Meta:
        model = MessMember
        fields = ["mess", "plan", "student", "staff"]

    def _kind(self, qs, name, value):
        return qs.filter(student__isnull=value != "student")


class VisitFilter(filters.FilterSet):
    date = filters.DateFilter(field_name="created_at", lookup_expr="date")

    class Meta:
        model = Visit
        fields = ["student", "status"]


class OutpassFilter(filters.FilterSet):
    class Meta:
        model = Outpass
        fields = ["student", "status", "is_late", "requested_by"]
