from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """`?page=` + `?page_size=` (capped) so the staff UI can show 10/25/50/100 rows."""

    page_size_query_param = "page_size"
    max_page_size = 200
