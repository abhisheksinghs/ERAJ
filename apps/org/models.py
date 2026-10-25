"""
Branches and role assignments (ADR-001, ADR-006). TENANT app: every client
schema has its own branches. A client with one campus has one Branch.

`RoleAssignment` lives here rather than in `apps.accounts` because accounts is
also a SHARED app (public-schema superadmins) and the public schema has no
`org_branch` table to point a foreign key at.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.mixins import SoftDelete, TimeStamped


class Branch(TimeStamped, SoftDelete):
    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=255)
    name_hi = models.CharField("name (Hindi)", max_length=255, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "branches"

    def __str__(self) -> str:
        return self.name


class BranchOwned(models.Model):
    """Abstract base for every branch-owned row. Filtering and stamping is done
    by `apps.org.mixins.BranchScopedViewSetMixin`; never set `branch` from
    request data."""

    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+", db_index=True)

    class Meta:
        abstract = True


class Role(models.TextChoices):
    ADMIN = "admin", "Admin"
    GROUP_ADMIN = "group_admin", "Group admin"
    ACCOUNTANT = "accountant", "Accountant"
    TEACHER = "teacher", "Teacher"
    LIBRARIAN = "librarian", "Librarian"
    WARDEN = "warden", "Warden"
    TRANSPORT = "transport", "Transport in-charge"
    HR = "hr", "HR"
    STORE = "store", "Store keeper"
    PARENT = "parent", "Parent"
    STUDENT = "student", "Student"


class RoleAssignment(TimeStamped):
    """A user holds `role` in `branch`. `branch` is NULL only for group admins,
    whose role applies to every branch of the client."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_assignments"
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    branch = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.CASCADE, related_name="role_assignments"
    )

    class Meta:
        ordering = ("user_id", "role")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "branch"],
                nulls_distinct=False,
                name="org_role_assignment_unique",
            ),
            models.CheckConstraint(
                check=Q(branch__isnull=False) | Q(role="group_admin"),
                name="org_only_group_admin_spans_branches",
            ),
            models.CheckConstraint(
                check=~Q(role="group_admin") | Q(branch__isnull=True),
                name="org_group_admin_has_no_branch",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} — {self.role} @ {self.branch or 'all branches'}"
