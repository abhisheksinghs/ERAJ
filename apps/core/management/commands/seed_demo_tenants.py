from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import Client, Domain, Module, Plan, PlanModule, Subscription


class Command(BaseCommand):
    help = "Seed demo tenants (ABC College, XYZ College) with plans + subscriptions"

    def handle(self, *args, **options):
        library, _ = Module.objects.get_or_create(code="library", defaults={"name": "Library"})
        attendance, _ = Module.objects.get_or_create(code="attendance", defaults={"name": "Attendance"})
        hostel, _ = Module.objects.get_or_create(code="hostel", defaults={"name": "Hostel"})

        basic, _ = Plan.objects.get_or_create(name="Basic", defaults={"price_per_year": 30000})
        standard, _ = Plan.objects.get_or_create(name="Standard", defaults={"price_per_year": 60000})

        PlanModule.objects.get_or_create(plan=basic, module=library)
        PlanModule.objects.get_or_create(plan=standard, module=library)
        PlanModule.objects.get_or_create(plan=standard, module=attendance)

        today = timezone.localdate()

        abc, created = Client.objects.get_or_create(
            schema_name="abc", defaults={"name": "ABC College", "slug": "abc"}
        )
        Domain.objects.get_or_create(domain="abc.localhost", tenant=abc, defaults={"is_primary": True})
        Subscription.objects.get_or_create(
            client=abc,
            defaults={
                "plan": basic,
                "status": Subscription.Status.ACTIVE,
                "start_date": today - timedelta(days=30),
                "end_date": today + timedelta(days=335),
            },
        )

        xyz, created = Client.objects.get_or_create(
            schema_name="xyz", defaults={"name": "XYZ College", "slug": "xyz"}
        )
        Domain.objects.get_or_create(domain="xyz.localhost", tenant=xyz, defaults={"is_primary": True})
        Subscription.objects.get_or_create(
            client=xyz,
            defaults={
                "plan": standard,
                "status": Subscription.Status.ACTIVE,
                "start_date": today - timedelta(days=10),
                "end_date": today + timedelta(days=355),
            },
        )

        self.stdout.write(self.style.SUCCESS("Seeded tenants: abc (Basic/library), xyz (Standard/library+attendance)"))
