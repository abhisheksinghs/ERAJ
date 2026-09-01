"""
Security-critical: a JWT minted for one tenant must NOT authenticate against
another tenant, and roles must be enforced. Uses real schemas (TenantTestCase).

    python manage.py test apps.accounts.tests.test_auth_isolation
"""
from django.core.cache import cache
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_context, tenant_context

from apps.accounts.models import User
from apps.core.models import Client, Domain, Module, Plan, PlanModule, Subscription

PW_A = "tenant-a-pw-9x"
PW_B = "tenant-b-pw-9x"


class AuthTenantIsolationTest(TenantTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with schema_context("public"):
            cls.other = Client.objects.create(
                schema_name="other_auth", name="Other College", slug="other-auth"
            )
            Domain.objects.create(domain="other-auth.localhost", tenant=cls.other, is_primary=True)
            plan = Plan.objects.create(name="P", price_per_year=0)
            lib = Module.objects.create(code="library", name="Library")
            PlanModule.objects.create(plan=plan, module=lib)
            today = timezone.localdate()
            for t in (cls.tenant, cls.other):
                Subscription.objects.create(
                    client=t,
                    plan=plan,
                    status=Subscription.Status.ACTIVE,
                    start_date=today,
                    end_date=today + timezone.timedelta(days=365),
                )
        with tenant_context(cls.tenant):
            User.objects.create_user(email="a@a.com", password=PW_A, role=User.Role.STAFF)
            User.objects.create_user(email="ro@a.com", password=PW_A, role=User.Role.READ_ONLY)
        with tenant_context(cls.other):
            User.objects.create_user(email="b@b.com", password=PW_B, role=User.Role.STAFF)

    @classmethod
    def tearDownClass(cls):
        with schema_context("public"):
            cls.other.delete(force_drop=True)
        cache.clear()
        super().tearDownClass()

    def setUp(self):
        cache.clear()  # reset the login throttle between tests

    def _token(self, client, email, password):
        r = client.post(
            "/api/auth/login/",
            {"email": email, "password": password},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["access"]

    def test_token_from_one_tenant_is_rejected_by_another(self):
        ca, cb = TenantClient(self.tenant), TenantClient(self.other)
        token_a = self._token(ca, "a@a.com", PW_A)

        same = ca.get("/api/library/books/", HTTP_AUTHORIZATION=f"Bearer {token_a}")
        self.assertEqual(same.status_code, 200)

        leaked = cb.get("/api/library/books/", HTTP_AUTHORIZATION=f"Bearer {token_a}")
        self.assertEqual(
            leaked.status_code,
            401,
            "CRITICAL: a token minted for one tenant authenticated against another",
        )

    def test_read_only_role_cannot_write(self):
        ca = TenantClient(self.tenant)
        token = self._token(ca, "ro@a.com", PW_A)
        self.assertEqual(
            ca.get("/api/library/books/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code, 200
        )
        post = ca.post(
            "/api/library/books/",
            {"title": "x", "author": "y", "isbn": "z"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(post.status_code, 403)

    def test_unauthenticated_is_rejected(self):
        self.assertEqual(TenantClient(self.tenant).get("/api/library/books/").status_code, 401)
