"""
THE most important test in this codebase: data created in one tenant's schema
is invisible from another tenant's schema, using REAL Postgres schemas.

    python manage.py test apps.library.tests.test_tenant_isolation
"""
from django.core.cache import cache
from django_tenants.utils import schema_context, tenant_context

from apps.core.models import Client, Domain
from apps.core.testing import EraTestCase, ensure_subscription
from apps.library.models import Book
from apps.org.models import Branch, Role


class TenantIsolationTest(EraTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with schema_context("public"):
            cls.other_tenant = Client.objects.create(
                schema_name="other_college", name="Other College", slug="other-college"
            )
            Domain.objects.create(domain="other.localhost", tenant=cls.other_tenant, is_primary=True)
            ensure_subscription(cls.other_tenant)
        with tenant_context(cls.other_tenant):
            cls.other_branch = Branch.objects.create(code="main", name="Other main")

    @classmethod
    def tearDownClass(cls):
        with schema_context("public"):
            cls.other_tenant.delete(force_drop=True)
        cache.clear()
        super().tearDownClass()

    def test_book_created_in_one_tenant_is_invisible_in_another(self):
        with tenant_context(self.tenant):
            Book.objects.create(branch=self.branch, title="Django", author="W. Vincent", isbn="ISBN-AAA-001")
            self.assertEqual(Book.objects.count(), 1)
        with tenant_context(self.other_tenant):
            self.assertEqual(
                Book.objects.count(),
                0,
                "CRITICAL FAILURE: tenant isolation broken (docs/FAILURE_MODES.md, search_path)",
            )
            Book.objects.create(branch=self.other_branch, title="Fluent", author="L. Ramalho", isbn="ISBN-BBB-002")
            Book.objects.filter(isbn="ISBN-BBB-002").delete()
        with tenant_context(self.tenant):
            self.assertEqual(Book.objects.count(), 1)
            self.assertEqual(Book.objects.first().isbn, "ISBN-AAA-001")

    def test_same_isbn_allowed_across_tenants(self):
        with tenant_context(self.tenant):
            Book.objects.create(branch=self.branch, title="Clean Code", author="R. Martin", isbn="ISBN-SHARED-999")
        with tenant_context(self.other_tenant):
            Book.objects.create(branch=self.other_branch, title="Clean Code", author="R. Martin", isbn="ISBN-SHARED-999")
            self.assertEqual(Book.objects.filter(isbn="ISBN-SHARED-999").count(), 1)
            Book.objects.filter(isbn="ISBN-SHARED-999").delete()

    def test_http_request_resolves_correct_tenant_schema(self):
        Book.objects.create(branch=self.branch, title="Tenant A Book", author="A", isbn="ISBN-HTTP-A")
        r = self.api(self.make_user(Role.LIBRARIAN)).get("/api/library/books/")
        self.assertEqual(r.json()["count"], 1)
        self.assertEqual(r.json()["results"][0]["isbn"], "ISBN-HTTP-A")
