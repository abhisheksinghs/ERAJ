from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.core.models import Client, Domain, Module, Plan, PlanModule, Subscription

User = get_user_model()

DEMO_PASSWORD = "eraj-demo-pass-123"  # dev only


class Command(BaseCommand):
    help = (
        "Seed 3 demo tenants matching the spec's own worked example "
        "(ABC=Basic/Library, XYZ=Standard/Library+Attendance, PQR=Premium/"
        "Library+Hostel+Attendance+HR+Payroll), plus every product's plan-gating."
    )

    def handle(self, *args, **options):
        modules = {
            code: Module.objects.get_or_create(code=code, defaults={"name": name})[0]
            for code, name in [
                ("library", "Library"),
                ("hostel", "Hostel"),
                ("attendance", "Attendance"),
                ("hr", "HR"),
                ("payroll", "Payroll"),
                ("fees", "Fees"),
                ("exam", "Exam"),
                ("transport", "Transport"),
                ("inventory", "Inventory"),
            ]
        }

        basic, _ = Plan.objects.get_or_create(name="Basic", defaults={"price_per_year": 30000})
        standard, _ = Plan.objects.get_or_create(name="Standard", defaults={"price_per_year": 60000})
        premium, _ = Plan.objects.get_or_create(name="Premium", defaults={"price_per_year": 120000})

        for plan, codes in [
            (basic, ["library"]),
            (standard, ["library", "hostel", "attendance"]),
            (premium, ["library", "hostel", "attendance", "hr", "payroll"]),
        ]:
            for code in codes:
                PlanModule.objects.get_or_create(plan=plan, module=modules[code])

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
        self._seed_tenant("abc", library=True, hostel=False, hr=False)

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
        self._seed_tenant("xyz", library=True, hostel=True, hr=False)

        pqr, _ = Client.objects.get_or_create(
            schema_name="pqr", defaults={"name": "PQR Institute", "slug": "pqr"}
        )
        Domain.objects.get_or_create(domain="pqr.localhost", tenant=pqr, defaults={"is_primary": True})
        Subscription.objects.get_or_create(
            client=pqr,
            defaults={
                "plan": premium,
                "status": Subscription.Status.ACTIVE,
                "start_date": today - timedelta(days=5),
                "end_date": today + timedelta(days=360),
            },
        )
        self._seed_tenant("pqr", library=True, hostel=True, hr=True)

        self.stdout.write(self.style.SUCCESS(
            "Seeded abc (Basic: library), xyz (Standard: library+hostel+attendance), "
            "pqr (Premium: library+hostel+attendance+hr+payroll).\n"
            f"Staff login per tenant: staff@<schema>.eraj.test / {DEMO_PASSWORD}"
        ))

    def _seed_tenant(self, schema_name: str, *, library: bool, hostel: bool, hr: bool):
        from apps.hostel.models import Room
        from apps.hr.models import Department, Employee
        from apps.library.models import Book

        with schema_context(schema_name):
            user, created = User.objects.get_or_create(
                email=f"staff@{schema_name}.eraj.test",
                defaults={"first_name": "Demo", "last_name": "Staff", "role": "staff"},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])

            if library:
                for title, author in [
                    ("Django for Professionals", "William S. Vincent"),
                    ("Fluent Python", "Luciano Ramalho"),
                    ("The Pragmatic Programmer", "Hunt & Thomas"),
                ]:
                    Book.objects.get_or_create(
                        isbn=f"{schema_name}-{title[:8].strip().lower().replace(' ', '')}",
                        defaults={"title": title, "author": author, "copies_total": 3, "copies_available": 3},
                    )

            if hostel:
                for number, capacity in [("A-101", 2), ("A-102", 2), ("B-201", 4)]:
                    Room.objects.get_or_create(number=number, defaults={"capacity": capacity})

            if hr:
                dept, _ = Department.objects.get_or_create(name="Administration")
                Employee.objects.get_or_create(
                    email=f"admin.staff@{schema_name}.eraj.test",
                    defaults={"full_name": "Admin Staff", "designation": "Administrator", "department": dept},
                )
