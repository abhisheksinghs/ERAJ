"""
THE most important test in this codebase.

Proves the core promise of the whole architecture: data created in one
tenant's schema is invisible from another tenant's schema, using REAL
Postgres schemas (not mocks). This is a `TenantTestCase` (django-tenants),
run via `manage.py test`, because it needs actual schema creation/switching
that pytest-django's transaction-per-test model doesn't provide out of the
box.

Run with:
    python manage.py test apps.library.tests.test_tenant_isolation
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context, tenant_context

from apps.accounts.models import User
from apps.core.models import Client, Domain, Module, Plan, PlanModule, Subscription
from apps.library.models import Book

ISO_PW = "iso-test-pw-9911"


class TenantIsolationTest(TenantTestCase):
    """
    django-tenants' TenantTestCase auto-creates `self.tenant` (schema
    "test") for the class. We create a SECOND tenant manually to prove
    cross-schema isolation, which is the actual thing we care about —
    a single tenant schema existing proves nothing about isolation.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with schema_context("public"):
            cls.other_tenant = Client.objects.create(
                schema_name="other_college", name="Other College", slug="other-college"
            )
            Domain.objects.create(domain="other.localhost", tenant=cls.other_tenant, is_primary=True)

            # Both tenants need an active Subscription including the
            # 'library' module, or SubscriptionEnforcementMiddleware
            # correctly (and by design) blocks every request with 402 —
            # which is what happened here before this fixture existed.
            plan = Plan.objects.create(name="Basic-Test", price_per_year=0)
            library_module = Module.objects.create(code="library", name="Library")
            PlanModule.objects.create(plan=plan, module=library_module)
            from django.utils import timezone

            today = timezone.localdate()
            for tenant in (cls.tenant, cls.other_tenant):
                Subscription.objects.create(
                    client=tenant,
                    plan=plan,
                    status=Subscription.Status.ACTIVE,
                    start_date=today,
                    end_date=today + timezone.timedelta(days=365),
                )

        # API access needs an authenticated per-schema user (auth is per-tenant).
        for tenant in (cls.tenant, cls.other_tenant):
            with tenant_context(tenant):
                User.objects.create_user(email="iso@test.local", password=ISO_PW, role="staff")

    @classmethod
    def tearDownClass(cls):
        with schema_context("public"):
            cls.other_tenant.delete(force_drop=True)
        from django.core.cache import cache

        cache.clear()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        cache.clear()  # reset the login throttle between tests

    def test_book_created_in_one_tenant_is_invisible_in_another(self):
        # Create a book in the primary test tenant's schema.
        with tenant_context(self.tenant):
            Book.objects.create(title="Django for Professionals", author="W. Vincent", isbn="ISBN-AAA-001")
            self.assertEqual(Book.objects.count(), 1)

        # Switch to the second tenant's schema — it must see ZERO books,
        # even though both schemas have an identical `library_book` table.
        with tenant_context(self.other_tenant):
            self.assertEqual(
                Book.objects.count(),
                0,
                "CRITICAL FAILURE: tenant isolation broken — a book created in "
                "one tenant schema is visible from another. This is the exact "
                "failure mode described in docs/FAILURE_MODES.md under "
                "'search_path not reset between requests'.",
            )
            Book.objects.create(title="Fluent Python", author="Luciano Ramalho", isbn="ISBN-BBB-002")
            self.assertEqual(Book.objects.count(), 1)

        # Back to the original tenant: must still see only its own book,
        # unaffected by what the other tenant just created.
        with tenant_context(self.tenant):
            self.assertEqual(Book.objects.count(), 1)
            self.assertEqual(Book.objects.first().isbn, "ISBN-AAA-001")

    def test_same_isbn_allowed_across_tenants(self):
        """
        isbn is unique PER SCHEMA (unique=True is a per-table constraint,
        and each tenant has its own physical table). Two different colleges
        independently cataloguing the same real-world book must not collide.
        """
        with tenant_context(self.tenant):
            Book.objects.create(title="Clean Code", author="Robert C. Martin", isbn="ISBN-SHARED-999")

        with tenant_context(self.other_tenant):
            # Must NOT raise IntegrityError — different schema, different table.
            Book.objects.create(title="Clean Code", author="Robert C. Martin", isbn="ISBN-SHARED-999")
            self.assertEqual(Book.objects.count(), 1)

    def _token(self, client):
        resp = client.post(
            "/api/auth/login/",
            {"email": "iso@test.local", "password": ISO_PW},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()["access"]

    def test_http_request_resolves_correct_tenant_schema(self):
        """
        End-to-end: an authenticated HTTP request to a tenant's domain must be
        served from that tenant's schema, exercising TenantMainMiddleware
        exactly as production traffic would.
        """
        with tenant_context(self.tenant):
            Book.objects.create(title="Tenant A Book", author="A", isbn="ISBN-HTTP-A")

        with tenant_context(self.other_tenant):
            Book.objects.create(title="Tenant B Book 1", author="B", isbn="ISBN-HTTP-B1")
            Book.objects.create(title="Tenant B Book 2", author="B", isbn="ISBN-HTTP-B2")

        client_a = TenantClient(self.tenant)
        client_b = TenantClient(self.other_tenant)
        auth_a = {"HTTP_AUTHORIZATION": f"Bearer {self._token(client_a)}"}
        auth_b = {"HTTP_AUTHORIZATION": f"Bearer {self._token(client_b)}"}

        resp_a = client_a.get("/api/library/books/", **auth_a)
        resp_b = client_b.get("/api/library/books/", **auth_b)

        self.assertEqual(resp_a.json()["count"], 1)
        self.assertEqual(resp_b.json()["count"], 2)
        self.assertEqual(resp_a.json()["results"][0]["isbn"], "ISBN-HTTP-A")
