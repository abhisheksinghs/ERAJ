"""
Atomic tenant onboarding: Client + Domain + Subscription + first Branch +
owner user (Admin of that branch and Group admin) — or none of it.

Usage:
    python manage.py create_tenant --name "ABC College" --slug abc \
        --domain abc.eraj.com --plan Standard --owner-email owner@abc.edu \
        --owner-password change-me-now [--branch-code main --branch-name "Main campus"]
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.core.models import Client, Domain, Plan, Subscription

User = get_user_model()


def current_academic_year(today: date) -> tuple[str, date, date]:
    """Indian academic session: April to March."""
    start_year = today.year if today.month >= 4 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}", date(start_year, 4, 1), date(start_year + 1, 3, 31)


def seed_tenant_basics(*, owner_email: str, owner_password: str, branch_code: str, branch_name: str):
    """Runs inside the tenant schema. Shared by create_tenant and the demo seed."""
    from apps.org.models import Branch, Role, RoleAssignment
    from apps.people.models import AcademicYear

    branch, _ = Branch.objects.get_or_create(code=branch_code, defaults={"name": branch_name})
    owner, created = User.objects.get_or_create(email=owner_email)
    if created:
        owner.set_password(owner_password)
        owner.save(update_fields=["password"])
    RoleAssignment.objects.get_or_create(user=owner, role=Role.ADMIN, branch=branch)
    RoleAssignment.objects.get_or_create(user=owner, role=Role.GROUP_ADMIN, branch=None)
    name, start, end = current_academic_year(timezone.localdate())
    AcademicYear.objects.get_or_create(
        name=name, defaults={"start_date": start, "end_date": end, "is_current": True}
    )
    return branch, owner


class Command(BaseCommand):
    help = "Onboard a new tenant (Client, Domain, Subscription, first branch, owner) atomically."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help='Institution name, e.g. "ABC College"')
        parser.add_argument("--slug", required=True, help="Schema name / subdomain, e.g. abc")
        parser.add_argument("--domain", required=True, help="Full domain, e.g. abc.eraj.com")
        parser.add_argument("--plan", required=True, help="Existing Plan name, e.g. Standard")
        parser.add_argument("--duration-days", type=int, default=365)
        parser.add_argument("--owner-email", required=True)
        parser.add_argument("--owner-password", required=True)
        parser.add_argument("--branch-code", default="main")
        parser.add_argument("--branch-name", default="")

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
            with schema_context(opts["slug"]), transaction.atomic():
                seed_tenant_basics(
                    owner_email=opts["owner_email"],
                    owner_password=opts["owner_password"],
                    branch_code=opts["branch_code"],
                    branch_name=opts["branch_name"] or opts["name"],
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
                f"owner {opts['owner_email']} (Admin of '{opts['branch_code']}' + Group admin)"
            )
        )
