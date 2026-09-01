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
    class Meta:
        model = Fine
        fields = ["member", "paid", "waived"]
