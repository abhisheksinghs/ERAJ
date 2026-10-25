from django.db.models import Q
from django_filters import rest_framework as filters

from apps.library.models import Book, Fine, Issue


class BookFilter(filters.FilterSet):
    available = filters.BooleanFilter(method="_available")
    tag = filters.CharFilter(field_name="tags", lookup_expr="contains")
    published_year__gte = filters.NumberFilter(field_name="published_year", lookup_expr="gte")
    published_year__lte = filters.NumberFilter(field_name="published_year", lookup_expr="lte")

    class Meta:
        model = Book
        fields = ["category", "publisher"]

    def _available(self, queryset, name, value):
        return queryset.filter(copies_available__gt=0) if value else queryset.filter(copies_available=0)


class IssueFilter(filters.FilterSet):
    open = filters.BooleanFilter(field_name="returned_at", lookup_expr="isnull")
    overdue = filters.BooleanFilter(method="_overdue")

    class Meta:
        model = Issue
        fields = ["book", "member"]

    def _overdue(self, queryset, name, value):
        from django.utils import timezone

        q = queryset.filter(returned_at__isnull=True, due_date__lt=timezone.localdate())
        return q if value else queryset.exclude(pk__in=q.values("pk"))


class FineFilter(filters.FilterSet):
    """`status` = open | paid | waived, counting fines paid at the fee counter
    (needs the `fee_outstanding` annotation from fines_with_fee_balance)."""

    status = filters.ChoiceFilter(
        choices=[("open", "Open"), ("paid", "Paid"), ("waived", "Waived")], method="_status"
    )

    class Meta:
        model = Fine
        fields = ["member", "paid", "waived"]

    def _status(self, qs, name, value):
        if value == "waived":
            return qs.filter(waived=True)
        desk_paid = Q(charge__isnull=True, paid=True)
        fees_paid = Q(charge__isnull=False, fee_outstanding__lte=0)
        if value == "paid":
            return qs.filter(desk_paid | fees_paid, waived=False)
        return qs.filter(waived=False).exclude(desk_paid | fees_paid)
