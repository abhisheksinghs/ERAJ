from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User


class RolePermission(BasePermission):
    """read_only role -> safe methods only; staff and owner -> all methods."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.role == User.Role.READ_ONLY:
            return request.method in SAFE_METHODS
        return True


class IsOwner(BasePermission):
    """Destructive / configuration actions."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.OWNER)
