from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied

from apps.org.mixins import PermissionedViewSetMixin
from apps.org.models import Branch, Role, RoleAssignment
from apps.org.rbac import roles_allow
from apps.org.scope import resolve_scope
from apps.org.serializers import BranchSerializer

User = get_user_model()

STAFF_ROLES = [r for r in Role.values if r not in (Role.PARENT, Role.STUDENT)]


class BranchViewSet(PermissionedViewSetMixin, viewsets.ModelViewSet):
    """Everyone with access sees their own branches; creating branches is a
    group-admin action (`org.branch.manage`, denied to branch admins)."""

    serializer_class = BranchSerializer
    perm_resource = "org.branch"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Branch.objects.none()
        return Branch.objects.filter(pk__in=resolve_scope(self.request).branch_ids)


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=STAFF_ROLES), write_only=True, required=False
    )
    branch_roles = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, min_length=10)

    class Meta:
        model = User
        fields = (
            "id", "email", "first_name", "last_name", "phone", "preferred_language", "is_active",
            "roles", "branch_roles", "password",
        )

    def get_branch_roles(self, obj) -> list[dict]:
        return [
            {"branch": a.branch_id, "role": a.role}
            for a in obj.role_assignments.all()
        ]


class UserViewSet(PermissionedViewSetMixin, viewsets.ModelViewSet):
    """Staff users who hold a role in the active branch. `roles` on write
    replaces the user's roles *in the active branch only*."""

    serializer_class = UserSerializer
    perm_resource = "org.user"
    search_fields = ["email", "first_name", "last_name", "phone"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        scope = resolve_scope(self.request)
        return (
            User.objects.filter(role_assignments__branch_id__in=scope.branch_ids)
            .prefetch_related("role_assignments")
            .distinct()
            .order_by("email")
        )

    def _branch(self):
        scope = resolve_scope(self.request)
        if scope.active is None:
            raise PermissionDenied("Choose a single branch to manage its users.")
        return scope.active

    @transaction.atomic
    def perform_create(self, serializer):
        branch = self._branch()
        roles = serializer.validated_data.pop("roles", [])
        password = serializer.validated_data.pop("password", None)
        self._check_assignable(roles)
        user = serializer.save()
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(update_fields=["password"])
        self._set_roles(user, branch, roles)

    @transaction.atomic
    def perform_update(self, serializer):
        branch = self._branch()
        # A branch admin must not edit (e.g. reset the password of) someone who
        # also holds roles elsewhere — that would hand them the other branch.
        reaches_outside = serializer.instance.role_assignments.exclude(branch=branch).exists()
        if reaches_outside and Role.GROUP_ADMIN not in resolve_scope(self.request).roles:
            raise PermissionDenied("This user has roles in other branches; ask a group admin.")
        roles = serializer.validated_data.pop("roles", None)
        password = serializer.validated_data.pop("password", None)
        user = serializer.save()
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        if roles is not None:
            self._check_assignable(roles)
            self._set_roles(user, branch, roles)

    def _check_assignable(self, roles):
        if Role.GROUP_ADMIN in roles and not roles_allow(set(resolve_scope(self.request).roles), "org.group_admin.assign"):
            raise PermissionDenied("Only a group admin can grant the group-admin role.")

    @staticmethod
    def _set_roles(user, branch, roles):
        RoleAssignment.objects.filter(user=user, branch=branch).delete()
        for role in roles:
            RoleAssignment.objects.get_or_create(
                user=user, role=role, branch=None if role == Role.GROUP_ADMIN else branch
            )
