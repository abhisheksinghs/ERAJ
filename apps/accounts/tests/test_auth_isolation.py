"""
Security-critical: a JWT minted for one tenant must NOT authenticate against
another tenant. Uses real schemas.

    python manage.py test apps.accounts.tests.test_auth_isolation
"""
from django.core.cache import cache
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context, tenant_context

from apps.accounts.models import User
from apps.core.models import Client, Domain
from apps.core.testing import TEST_PASSWORD, EraTestCase, access_token, ensure_subscription
from apps.org.models import Branch, Role, RoleAssignment


class AuthTenantIsolationTest(EraTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with schema_context("public"):
            cls.other = Client.objects.create(schema_name="other_auth", name="Other College", slug="other-auth")
            Domain.objects.create(domain="other-auth.localhost", tenant=cls.other, is_primary=True)
            ensure_subscription(cls.other)
        with tenant_context(cls.other):
            branch = Branch.objects.create(code="main", name="Other main")
            cls.other_user = User.objects.create_user(email="b@b.com", password=TEST_PASSWORD)
            RoleAssignment.objects.create(user=cls.other_user, role=Role.LIBRARIAN, branch=branch)

    @classmethod
    def tearDownClass(cls):
        with schema_context("public"):
            cls.other.delete(force_drop=True)
        cache.clear()
        super().tearDownClass()

    def test_login_endpoint_issues_a_working_token(self):
        self.make_user(Role.LIBRARIAN, email="a@a.com")
        client = TenantClient(self.tenant)
        r = client.post(
            "/api/auth/login/", {"email": "a@a.com", "password": TEST_PASSWORD}, content_type="application/json"
        )
        self.assertEqual(r.status_code, 200, r.content)
        ok = client.get("/api/library/books/", HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        self.assertEqual(ok.status_code, 200)

    def test_token_from_one_tenant_is_rejected_by_another(self):
        user = self.make_user(Role.LIBRARIAN)
        token_a = access_token(user)
        same = TenantClient(self.tenant).get("/api/library/books/", HTTP_AUTHORIZATION=f"Bearer {token_a}")
        self.assertEqual(same.status_code, 200)
        leaked = TenantClient(self.other).get("/api/library/books/", HTTP_AUTHORIZATION=f"Bearer {token_a}")
        self.assertEqual(leaked.status_code, 401, "CRITICAL: a token minted for one tenant authenticated against another")

    def test_wrong_password_is_rejected(self):
        self.make_user(Role.LIBRARIAN, email="c@a.com")
        r = TenantClient(self.tenant).post(
            "/api/auth/login/", {"email": "c@a.com", "password": "nope"}, content_type="application/json"
        )
        self.assertEqual(r.status_code, 401)

    def test_unauthenticated_is_rejected(self):
        self.assertEqual(TenantClient(self.tenant).get("/api/library/books/").status_code, 401)
