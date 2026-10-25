from rest_framework.pagination import PageNumberPagination

EXPORT_FORMATS = {"xlsx", "csv"}


class StandardPagination(PageNumberPagination):
    """`?page=` + `?page_size=` (capped) so the staff UI can show 10/25/50/100
    rows. Excel/CSV exports (`?format=xlsx|csv`) are not paginated — the
    renderer caps them at EXPORT_MAX_ROWS."""

    page_size_query_param = "page_size"
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        renderer = getattr(request, "accepted_renderer", None)
        if getattr(renderer, "format", None) in EXPORT_FORMATS:
            return None
        return super().paginate_queryset(queryset, request, view)
