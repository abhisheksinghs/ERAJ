from django.db import connection
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.authentication import SCHEMA_CLAIM
from apps.accounts.models import User


class SchemaScopedTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # SimpleJWT copies custom claims from the refresh token onto every
        # refreshed access token, so setting this once here is enough.
        # Roles are NOT put in the token: they are read per request from
        # RoleAssignment so a revoked role takes effect immediately.
        token[SCHEMA_CLAIM] = connection.schema_name
        return token


class SchemaScopedTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs["refresh"])
        except TokenError as exc:
            raise InvalidToken(str(exc)) from exc
        if refresh.get(SCHEMA_CLAIM) != connection.schema_name:
            raise InvalidToken("refresh token was issued for a different tenant")
        return super().validate(attrs)


class MeSerializer(serializers.ModelSerializer):
    branches = serializers.SerializerMethodField()
    group_admin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "email", "first_name", "last_name", "phone", "preferred_language",
            "group_admin", "branches",
        )
        read_only_fields = ("email", "group_admin", "branches")

    def get_group_admin(self, obj) -> bool:
        from apps.org.models import Role

        return obj.role_assignments.filter(role=Role.GROUP_ADMIN).exists()

    def get_branches(self, obj) -> list[dict]:
        """Every branch the user can act in, with the roles and the permission
        patterns that apply there — the frontend evaluates the same patterns
        (apps/org/rbac.py) to build menus and hide buttons. The server still
        checks every request."""
        from apps.org.models import Branch
        from apps.org.rbac import PERMISSIONS
        from apps.org.scope import allowed_branch_ids, roles_for

        out = []
        for branch in Branch.objects.filter(pk__in=allowed_branch_ids(obj)).order_by("name"):
            roles = sorted(roles_for(obj, branch.pk))
            out.append(
                {
                    "id": branch.pk,
                    "code": branch.code,
                    "name": branch.name,
                    "name_hi": branch.name_hi,
                    "roles": roles,
                    "permissions": {r: PERMISSIONS.get(r, []) for r in roles},
                }
            )
        return out
