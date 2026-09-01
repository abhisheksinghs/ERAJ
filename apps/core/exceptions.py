from rest_framework.exceptions import APIException


class Conflict(APIException):
    """Business-rule violation on an otherwise valid request (book unavailable,
    room full, resident already allocated, ...)."""

    status_code = 409
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


class UpstreamError(APIException):
    status_code = 502
    default_detail = "An upstream service failed."
    default_code = "upstream_error"
