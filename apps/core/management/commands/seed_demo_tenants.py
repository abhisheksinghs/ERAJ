from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.core.models import Client, Domain, Module, Plan, PlanModule, Subscription

User = get_user_model()

DEMO_PASSWORD = "eraj-demo-pass-123"  # dev only


class Command(BaseCommand):
    help = "Seed demo tenants (ABC College, XYZ College) with plans, subscriptions, a staff user, and sample module data"

    def handle(self, *args, **options):
        library, _ = Module.objects.get_or_create(code="library", defaults={"name": "Library"})
        attendance, _ = Module.objects.get_or_create(code="attendance", defaults={"name": "Attendance"})
        hostel, _ = Module.objects.get_or_create(code="hostel", defaults={"name": "Hostel"})

        basic, _ = Plan.objects.get_or_create(name="Basic", defaults={"price_per_year": 30000})
        standard, _ = Plan.objects.get_or_create(name="Standard", defaults={"price_per_year": 60000})

        PlanModule.objects.get_or_create(plan=basic, module=library)
        PlanModule.objects.get_or_create(plan=standard, module=library)
        PlanModule.objects.get_or_create(plan=standard, module=attendance)
        PlanModule.objects.get_or_create(plan=standard, module=hostel)

        today = timezone.localdate()

        abc, _ = Client.objects.get_or_create(
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
        self._seed_tenant("abc", with_hostel=False)

        xyz, _ = Client.objects.get_or_create(
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
        self._seed_tenant("xyz", with_hostel=True)

        self.stdout.write(self.style.SUCCESS(
            "Seeded abc (Basic: library) and xyz (Standard: library+attendance+hostel).\n"
            f"Staff login per tenant: staff@<schema>.eraj.test / {DEMO_PASSWORD}"
        ))

    def _seed_tenant(self, schema_name: str, *, with_hostel: bool):
        from apps.hostel.models import Room
        from apps.library.models import Book

        with schema_context(schema_name):
            user, created = User.objects.get_or_create(
                email=f"staff@{schema_name}.eraj.test",
                defaults={"first_name": "Demo", "last_name": "Staff", "role": "staff"},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])

            for title, author in [
                ("Django for Professionals", "William S. Vincent"),
                ("Fluent Python", "Luciano Ramalho"),
                ("The Pragmatic Programmer", "Hunt & Thomas"),
            ]:
                Book.objects.get_or_create(
                    isbn=f"{schema_name}-{title[:8].strip().lower().replace(' ', '')}",
                    defaults={"title": title, "author": author, "copies_total": 3, "copies_available": 3},
                )

            if with_hostel:
                for number, capacity in [("A-101", 2), ("A-102", 2), ("B-201", 4)]:
                    Room.objects.get_or_create(number=number, defaults={"capacity": capacity})
