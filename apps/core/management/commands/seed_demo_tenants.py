"""
Demo data for local development and staging walkthroughs. Never run in prod.

    abc  — Basic plan (library), one branch
    pqr  — Premium plan (every module), two branches (Patna, Gaya) with
           a group admin, a librarian, an accountant, a teacher and a warden

All demo users share DEMO_PASSWORD.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.core.management.commands.create_tenant import seed_tenant_basics
from apps.core.models import Client, Domain, Module, Plan, PlanModule, Subscription

User = get_user_model()

DEMO_PASSWORD = "eraj-demo-pass-123"  # dev only

MODULES = [
    ("library", "Library"),
    ("hostel", "Hostel and Mess"),
    ("attendance", "Attendance"),
    ("hr", "HR"),
    ("payroll", "Payroll"),
    ("fees", "Fees"),
    ("exam", "Exam"),
    ("transport", "Transport"),
    ("inventory", "Inventory"),
    ("timetable", "Timetable"),
    ("learning", "Homework and online learning"),
]


class Command(BaseCommand):
    help = "Seed demo tenants: abc (Basic, 1 branch) and pqr (Premium, 2 branches)."

    def handle(self, *args, **options):
        modules = {code: Module.objects.get_or_create(code=code, defaults={"name": name})[0] for code, name in MODULES}
        basic, _ = Plan.objects.get_or_create(name="Basic", defaults={"price_per_year": 30000})
        premium, _ = Plan.objects.get_or_create(name="Premium", defaults={"price_per_year": 120000})
        PlanModule.objects.get_or_create(plan=basic, module=modules["library"])
        for module in modules.values():
            PlanModule.objects.get_or_create(plan=premium, module=module)

        today = timezone.localdate()
        for schema, name, plan in [("abc", "ABC College", basic), ("pqr", "PQR Educational Trust", premium)]:
            client, _ = Client.objects.get_or_create(schema_name=schema, defaults={"name": name, "slug": schema})
            Domain.objects.get_or_create(domain=f"{schema}.localhost", tenant=client, defaults={"is_primary": True})
            Subscription.objects.get_or_create(
                client=client,
                defaults={
                    "plan": plan,
                    "status": Subscription.Status.ACTIVE,
                    "start_date": today - timedelta(days=30),
                    "end_date": today + timedelta(days=335),
                },
            )

        with schema_context("abc"):
            branch, _ = seed_tenant_basics(
                owner_email="owner@abc.eraj.test", owner_password=DEMO_PASSWORD,
                branch_code="main", branch_name="ABC College",
            )
            self._library(branch)

        with schema_context("pqr"):
            patna, _ = seed_tenant_basics(
                owner_email="owner@pqr.eraj.test", owner_password=DEMO_PASSWORD,
                branch_code="patna", branch_name="Patna campus",
            )
            from apps.org.models import Branch

            gaya, _ = Branch.objects.get_or_create(code="gaya", defaults={"name": "Gaya campus"})
            for branch in (patna, gaya):
                self._staff_users(branch)
                self._people(branch)
                self._library(branch)
                self._hostel(branch)

        self.stdout.write(self.style.SUCCESS(
            "Seeded abc (Basic, 1 branch) and pqr (Premium, branches patna + gaya).\n"
            f"Password for every demo user: {DEMO_PASSWORD}\n"
            "  owner@abc.eraj.test, owner@pqr.eraj.test (Admin + Group admin)\n"
            "  <role>.<branch>@pqr.eraj.test for librarian/accountant/teacher/warden, e.g. librarian.patna@pqr.eraj.test"
        ))

    @staticmethod
    def _staff_users(branch):
        from apps.org.models import Role, RoleAssignment

        for role in (Role.LIBRARIAN, Role.ACCOUNTANT, Role.TEACHER, Role.WARDEN):
            user, created = User.objects.get_or_create(
                email=f"{role}.{branch.code}@pqr.eraj.test",
                defaults={"first_name": role.label, "last_name": branch.name},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
            RoleAssignment.objects.get_or_create(user=user, role=role, branch=branch)

    @staticmethod
    def _people(branch):
        from apps.people.models import (
            AcademicYear, Department, Enrollment, Guardian, Program, Section, Staff, Student,
            StudentGuardian, Subject,
        )

        year = AcademicYear.objects.get(is_current=True)
        dept, _ = Department.objects.get_or_create(branch=branch, name="Teaching")
        teacher, _ = Staff.objects.get_or_create(
            branch=branch, employee_code=f"{branch.code.upper()}-T001",
            defaults={"full_name": "Sunita Kumari", "designation": "TGT Mathematics", "department": dept},
        )
        for seq, (code, name) in enumerate([("C6", "Class 6"), ("C7", "Class 7")], start=6):
            program, _ = Program.objects.get_or_create(
                branch=branch, code=code, defaults={"name": name, "sequence": seq}
            )
            section, _ = Section.objects.get_or_create(
                branch=branch, academic_year=year, program=program, term=None, name="A",
                defaults={"class_teacher": teacher},
            )
            for subj in ("Mathematics", "Science", "Hindi", "English"):
                Subject.objects.get_or_create(
                    branch=branch, code=f"{code}-{subj[:3].upper()}", defaults={"name": subj, "program": program}
                )
            for i in range(1, 6):
                adm = f"{branch.code.upper()}-{code}-{i:03d}"
                student, created = Student.objects.get_or_create(
                    branch=branch, admission_no=adm,
                    defaults={"full_name": f"Student {code}-{i}", "gender": "male" if i % 2 else "female"},
                )
                if created:
                    Enrollment.objects.create(
                        branch=branch, student=student, academic_year=year, program=program,
                        section=section, roll_no=str(i),
                    )
                    guardian = Guardian.objects.create(
                        branch=branch, full_name=f"Guardian of {student.full_name}", phone=f"98000{seq}{i:04d}"
                    )
                    StudentGuardian.objects.create(
                        branch=branch, student=student, guardian=guardian, relation="father", is_primary=True
                    )

    @staticmethod
    def _library(branch):
        from apps.library.models import Book

        for title, author in [
            ("Django for Professionals", "William S. Vincent"),
            ("Fluent Python", "Luciano Ramalho"),
            ("The Pragmatic Programmer", "Hunt & Thomas"),
        ]:
            Book.objects.get_or_create(
                branch=branch,
                isbn=f"{branch.code}-{title[:8].strip().lower().replace(' ', '')}",
                defaults={"title": title, "author": author, "copies_total": 3, "copies_available": 3},
            )

    @staticmethod
    def _hostel(branch):
        from apps.hostel.models import Room

        for number, capacity in [("A-101", 2), ("A-102", 2), ("B-201", 4)]:
            Room.objects.get_or_create(branch=branch, number=number, defaults={"capacity": capacity})
