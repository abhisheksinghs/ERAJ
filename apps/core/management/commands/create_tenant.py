"""
Atomic tenant onboarding: Client + Domain + Subscription + owner user, or
none of it. Closes docs/REQUIREMENTS_GAP_ANALYSIS.md §7 ("one atomic
onboarding action" — today's alternative is three separate admin screens
with no rollback between them).

Usage:
    python manage.py create_tenant --name "ABC College" --slug abc \
        --domain abc.eraj.com --plan Standard --owner-email owner@abc.edu \
        --owner-password change-me-now
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.core.models import Client, Domain, Plan, Subscription

User = get_user_model()


class Command(BaseCommand):
    help = "Onboard a new tenant (Client + Domain + Subscription + owner user) atomically."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help='Institution name, e.g. "ABC College"')
        parser.add_argument("--slug", required=True, help="Schema name / subdomain, e.g. abc")
        parser.add_argument("--domain", required=True, help="Full domain, e.g. abc.eraj.com")
        parser.add_argument("--plan", required=True, help="Existing Plan name, e.g. Standard")
        parser.add_argument("--duration-days", type=int, default=365)
        parser.add_argument("--owner-email", required=True)
        parser.add_argument("--owner-password", required=True)

    def handle(self, *args, **opts):
        try:
            plan = Plan.objects.get(name=opts["plan"])
        except Plan.DoesNotExist as exc:
            raise CommandError(f"No such plan: {opts['plan']!r}") from exc

        if Client.objects.filter(schema_name=opts["slug"]).exists():
            raise CommandError(f"Tenant {opts['slug']!r} already exists")

        client = None
        try:
            with transaction.atomic():
                client = Client.objects.create(
                    schema_name=opts["slug"], name=opts["name"], slug=opts["slug"]
                )
                Domain.objects.create(domain=opts["domain"], tenant=client, is_primary=True)
                today = timezone.localdate()
                Subscription.objects.create(
                    client=client,
                    plan=plan,
                    status=Subscription.Status.ACTIVE,
                    start_date=today,
                    end_date=today + timedelta(days=opts["duration_days"]),
                )
            with schema_context(opts["slug"]):
                User.objects.create_user(
                    email=opts["owner_email"], password=opts["owner_password"], role="owner"
                )
        except Exception:
            # Whatever succeeded before the failure — including the schema
            # itself, created as a side effect of Client.save() — gets torn
            # down so a retry doesn't collide with a half-onboarded tenant.
            if client is not None and Client.objects.filter(pk=client.pk).exists():
                client.delete(force_drop=True)
            raise

        self.stdout.write(
            self.style.SUCCESS(
                f"Onboarded '{opts['name']}' ({opts['slug']}) on plan {opts['plan']}, "
                f"owner {opts['owner_email']}"
            )
        )
