"""
Shared base for tenant tests.

    class LendingTest(EraTestCase):
        def test_x(self):
            student = self.make_student()
            api = self.api(self.make_user("librarian"))
            r = api.get("/api/library/books/")

`EraTestCase` runs inside django-tenants' test tenant (schema "test"). Public-
schema fixtures (plan, modules, subscription) are created with get_or_create so
any number of test classes can run in one invocation — the old per-class
`Module.objects.create(...)` collided on `core_module_code_key`.
"""
from __future__ import annotations

import itertools
from datetime import date, timedelta

from django.core.cache import cache
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context

from apps.core.models import Module, Plan, PlanModule, Subscription

ALL_MODULES = [
    "library", "hostel", "attendance", "hr", "payroll", "fees", "exam",
    "transport", "inventory", "timetable", "learning",
]
TEST_PASSWORD = "era-test-pass-4242"
_seq = itertools.count(1)


def ensure_full_plan() -> Plan:
    plan, _ = Plan.objects.get_or_create(name="Test-All", defaults={"price_per_year": 0})
    for code in ALL_MODULES:
        module, _ = Module.objects.get_or_create(code=code, defaults={"name": code.title()})
        PlanModule.objects.get_or_create(plan=plan, module=module)
    return plan


def ensure_subscription(client) -> None:
    today = timezone.localdate()
    Subscription.objects.get_or_create(
        client=client,
        defaults={
            "plan": ensure_full_plan(),
            "status": Subscription.Status.ACTIVE,
            "start_date": today - timedelta(days=1),
            "end_date": today + timedelta(days=365),
        },
    )


def access_token(user) -> str:
    """Mint a schema-bound access token without going through the throttled
    login endpoint. Must be called inside the user's tenant schema."""
    from apps.accounts.serializers import SchemaScopedTokenObtainPairSerializer

    return str(SchemaScopedTokenObtainPairSerializer.get_token(user).access_token)


class EraTestCase(TenantTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with schema_context("public"):
            ensure_subscription(cls.tenant)

    def setUp(self):
        super().setUp()
        # A request to another tenant (cross-tenant tests) leaves the shared
        # connection on that tenant's schema; pin it back before writing.
        from django.db import connection

        connection.set_tenant(self.tenant)
        cache.clear()  # subscription-state cache + login throttle
        from apps.org.models import Branch
        from apps.people.models import AcademicYear

        self.branch = Branch.objects.create(code="main", name="Main campus")
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=date(2026, 4, 1), end_date=date(2027, 3, 31), is_current=True
        )

    # ---- factories -------------------------------------------------------
    def make_branch(self, code: str):
        from apps.org.models import Branch

        return Branch.objects.create(code=code, name=code.title())

    def make_user(self, role: str | None = None, branch=None, email: str | None = None):
        from apps.accounts.models import User
        from apps.org.models import Role, RoleAssignment

        user = User.objects.create_user(email=email or f"u{next(_seq)}@test.local", password=TEST_PASSWORD)
        if role:
            RoleAssignment.objects.create(
                user=user, role=role, branch=None if role == Role.GROUP_ADMIN else (branch or self.branch)
            )
        return user

    def make_student(self, branch=None, **kw):
        from apps.people.models import Student

        n = next(_seq)
        kw.setdefault("admission_no", f"ADM-{n}")
        kw.setdefault("full_name", f"Student {n}")
        return Student.objects.create(branch=branch or self.branch, **kw)

    def make_staff(self, branch=None, **kw):
        from apps.people.models import Staff

        n = next(_seq)
        kw.setdefault("employee_code", f"EMP-{n}")
        kw.setdefault("full_name", f"Staff {n}")
        return Staff.objects.create(branch=branch or self.branch, **kw)

    def make_member(self, student=None, **kw):
        from apps.library.models import Member

        student = student or self.make_student(branch=kw.pop("branch", None))
        return Member.objects.create(branch=student.branch, student=student, **kw)

    # ---- API -------------------------------------------------------------
    def api(self, user, branch: object = "default") -> TenantClient:
        """Client authenticated as `user`, sending X-Branch for `branch`
        (default: self.branch; None: no header; "all": all branches)."""
        headers = {"HTTP_AUTHORIZATION": f"Bearer {access_token(user)}"}
        if branch == "default":
            branch = self.branch
        if branch is not None:
            headers["HTTP_X_BRANCH"] = branch if isinstance(branch, str) else str(branch.pk)
        return TenantClient(self.tenant, **headers)
