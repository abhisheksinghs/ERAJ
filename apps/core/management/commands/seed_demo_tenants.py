"""
Demo data for local development and staging walkthroughs. Never run in prod.

    abc  — Basic plan (library), one branch
    pqr  — Premium plan (every module), two branches (Patna, Gaya) with
           a group admin, a librarian, an accountant, a teacher and a warden

All demo users share DEMO_PASSWORD.
"""
from datetime import timedelta
from decimal import Decimal

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
                self._fees(branch)
                self._academics(branch)
                self._timetable(branch)

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
    def _academics(branch):
        """Teacher login ↔ staff record, teaching allocation, holidays, a gate
        device with cards, a month of attendance, and a graded Half-Yearly."""
        import random
        from datetime import date, timedelta

        from apps.attendance import services as att
        from apps.attendance.models import AttendanceCard, AttendanceDevice, Holiday
        from apps.exam import services as exam_services
        from apps.exam.models import Exam, ExamSubject, GradeBand, GradeScale
        from apps.people.models import AcademicYear, Enrollment, Section, Staff, Subject, TeachingAssignment

        year = AcademicYear.objects.get(is_current=True)
        teacher = Staff.objects.get(branch=branch, employee_code=f"{branch.code.upper()}-T001")
        user = User.objects.filter(email=f"teacher.{branch.code}@pqr.eraj.test").first()
        if user and teacher.user_id is None:
            teacher.user = user
            teacher.save(update_fields=["user", "updated_at"])
        for section in Section.objects.filter(branch=branch, academic_year=year):
            maths = Subject.objects.get(branch=branch, code=f"{section.program.code}-MAT")
            TeachingAssignment.objects.get_or_create(branch=branch, staff=teacher, subject=maths, section=section,
                                                     defaults={"periods_per_week": 6})

        for d, name, hi in [(date(year.start_date.year, 10, 2), "Gandhi Jayanti", "गांधी जयंती"),
                            (date(year.start_date.year, 10, 20), "Dussehra", "दशहरा"),
                            (date(year.start_date.year, 11, 8), "Diwali", "दीपावली"),
                            (date(year.start_date.year, 11, 15), "Chhath Puja", "छठ पूजा")]:
            Holiday.objects.get_or_create(branch=branch, date=d, defaults={"name": name, "name_hi": hi})

        AttendanceDevice.objects.get_or_create(serial_no=f"{branch.code.upper()}-GATE-01",
                                               defaults={"branch": branch, "name": "Main gate", "brand": "zkteco", "location": "Main gate"})
        rng = random.Random(branch.code)
        sections = list(Section.objects.filter(branch=branch, academic_year=year).order_by("program__sequence"))
        for i, enr in enumerate(Enrollment.objects.filter(section__in=sections).select_related("student").order_by("pk"), start=1):
            AttendanceCard.objects.get_or_create(branch=branch, code=f"{1000 + i}", defaults={"student": enr.student})

        today = timezone.localdate()
        start = today.replace(day=1) - timedelta(days=1)
        start = start.replace(day=1)  # from the 1st of last month
        for section in sections:
            students = att.section_students(section)
            d = start
            while d < today:
                if d not in att.non_working_days(branch, d, d) and not att.AttendanceRecord.objects.filter(section=section, date=d).exists():
                    absent = [s.pk for s in students if rng.random() < (0.35 if s.admission_no.endswith("-005") else 0.06)]
                    att.mark_section(section=section, on=d, statuses={}, absent=absent, by="seed", can_correct_past=True)
                d += timedelta(days=1)

        scale, created = GradeScale.objects.get_or_create(branch=branch, name="CBSE 8-point")
        if created:
            for grade, low, gp in [("A1", 91, 10), ("A2", 81, 9), ("B1", 71, 8), ("B2", 61, 7), ("C1", 51, 6), ("C2", 41, 5), ("D", 33, 4), ("E", 0, 0)]:
                GradeBand.objects.create(scale=scale, grade=grade, min_percent=low, grade_point=gp, is_fail=grade == "E")
        for section in sections:
            program = section.program
            half, created = Exam.objects.get_or_create(branch=branch, academic_year=year, program=program, name="Half-Yearly",
                                                       defaults={"scale": scale, "weightage": 30, "sequence": 1})
            Exam.objects.get_or_create(branch=branch, academic_year=year, program=program, name="Annual",
                                       defaults={"scale": scale, "weightage": 70, "sequence": 2})
            if not created:
                continue
            for n, subj in enumerate(Subject.objects.filter(branch=branch, program=program).order_by("code"), start=1):
                es = ExamSubject.objects.create(branch=branch, exam=half, subject=subj, max_theory=80, max_practical=20,
                                                pass_marks=33, sequence=n, date=year.start_date.replace(month=9, day=14 + n),
                                                start_time="09:30")
                rows = []
                for s in att.section_students(section):
                    if rng.random() < 0.04:
                        rows.append({"student": s.pk, "status": "absent"})
                    else:
                        rows.append({"student": s.pk, "theory": Decimal(rng.randint(28, 78)), "practical": Decimal(rng.randint(12, 20))})
                exam_services.save_marks(exam_subject=es, section=section, rows=rows, by="seed")

    @staticmethod
    def _timetable(branch):
        """Four more teachers, a full teaching allocation, a Mon–Sat bell schedule,
        rooms, and a week's timetable for both sections."""
        from datetime import time

        from apps.people.models import AcademicYear, Department, Section, Staff, Subject, TeachingAssignment
        from apps.timetable import services as tt
        from apps.timetable.models import BellSchedule, PeriodSlot, Room, TimetableEntry

        year = AcademicYear.objects.get(is_current=True)
        dept = Department.objects.get(branch=branch, name="Teaching")
        code = branch.code.upper()
        staff = {"MAT": Staff.objects.get(branch=branch, employee_code=f"{code}-T001")}
        for n, (name, subj) in enumerate([("Rakesh Prasad", "SCI"), ("Meena Kumari", "HIN"), ("Arvind Singh", "ENG"),
                                          ("Pooja Sinha", "MAT")], start=2):
            staff.setdefault(subj, None)
            obj, _ = Staff.objects.get_or_create(branch=branch, employee_code=f"{code}-T00{n}",
                                                 defaults={"full_name": name, "designation": "TGT", "department": dept})
            if subj == "MAT":
                staff["MAT2"] = obj
            else:
                staff[subj] = obj
        schedule, created = BellSchedule.objects.get_or_create(branch=branch, name="Regular (Mon–Sat)", defaults={"is_default": True})
        if created:
            for n, (a, b, label, brk) in enumerate([
                ("08:00", "08:40", "Period 1", False), ("08:40", "09:20", "Period 2", False), ("09:20", "10:00", "Period 3", False),
                ("10:00", "10:20", "Break", True), ("10:20", "11:00", "Period 4", False), ("11:00", "11:40", "Period 5", False),
                ("11:40", "12:20", "Period 6", False)], start=1):
                PeriodSlot.objects.create(schedule=schedule, number=n, label=label, start=time.fromisoformat(a),
                                          end=time.fromisoformat(b), is_break=brk, days="0,1,2,3,4,5")
        for name in ("Room 6A", "Room 7A", "Science lab"):
            Room.objects.get_or_create(branch=branch, name=name)
        sections = list(Section.objects.filter(branch=branch, academic_year=year).order_by("program__sequence"))
        if TimetableEntry.objects.filter(section__in=sections).exists():
            return
        slots = list(schedule.slots.filter(is_break=False).order_by("number"))
        for si, section in enumerate(sections):
            assign = {}
            for subj_code, teacher_key in (("MAT", "MAT" if si == 0 else "MAT2"), ("SCI", "SCI"), ("HIN", "HIN"), ("ENG", "ENG")):
                subject = Subject.objects.get(branch=branch, code=f"{section.program.code}-{subj_code}")
                assign[subj_code], _ = TeachingAssignment.objects.get_or_create(
                    branch=branch, staff=staff[teacher_key], subject=subject, section=section, defaults={"periods_per_week": 9})
            room = Room.objects.get(branch=branch, name=f"Room {section.program.code[1:]}A")
            order = ["MAT", "SCI", "HIN", "ENG"]
            for day in range(6):
                for k, slot in enumerate(slots):
                    subj = order[(k + day + si) % 4]
                    try:
                        tt.place(section=section, day=day, slot=slot, assignment=assign[subj], room=room, by="seed")
                    except Exception:  # a clash: leave the period free in the demo
                        continue

    @staticmethod
    def _fees(branch):
        """Tuition in four quarterly instalments per class; the first is already due."""
        from apps.fees import services
        from apps.fees.models import FeeHead, FeePlan, FeePlanInstalment
        from apps.people.models import AcademicYear, Program

        year = AcademicYear.objects.get(is_current=True)
        tuition, _ = FeeHead.objects.get_or_create(
            branch=branch, code="TUI",
            defaults={"name": "Tuition fee", "name_hi": "शिक्षण शुल्क", "kind": FeeHead.Kind.TUITION,
                      "late_fine_mode": FeeHead.LateFine.PER_DAY, "late_fine_amount": 5, "grace_days": 10},
        )
        FeeHead.objects.get_or_create(
            branch=branch, code="EXM", defaults={"name": "Exam fee", "name_hi": "परीक्षा शुल्क", "kind": FeeHead.Kind.EXAM}
        )
        start = year.start_date
        quarters = [(1, "Q1 (Apr–Jun)", 0), (2, "Q2 (Jul–Sep)", 3), (3, "Q3 (Oct–Dec)", 6), (4, "Q4 (Jan–Mar)", 9)]
        for program in Program.objects.filter(branch=branch):
            amount = 3000 + 250 * (program.sequence or 0)
            plan, created = FeePlan.objects.get_or_create(
                branch=branch, academic_year=year, program=program, head=tuition,
                defaults={"name": f"{program.name} tuition {year.name}"},
            )
            if created:
                for seq, label, months in quarters:
                    m = start.month - 1 + months
                    due = start.replace(year=start.year + m // 12, month=m % 12 + 1, day=10)
                    FeePlanInstalment.objects.create(plan=plan, sequence=seq, label=label, due_date=due, amount=amount)
            services.apply_plan(plan)

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
        """Two blocks, a hostel fee, a contractor-run mess with rates and a menu,
        and two residents (so the Fees account shows hostel + mess charges)."""
        from apps.hostel import services
        from apps.hostel.models import Block, HostelFeeRule, MenuItem, Mess, MessMealRate, Room
        from apps.people.models import Student

        boys, _ = Block.objects.get_or_create(branch=branch, code="BH", defaults={"name": "Boys hostel", "gender": "male"})
        girls, _ = Block.objects.get_or_create(branch=branch, code="GH", defaults={"name": "Girls hostel", "gender": "female"})
        for block in (boys, girls):
            for number, capacity, kind in [("101", 2, "double"), ("102", 2, "double"), ("201", 4, "dorm")]:
                Room.objects.get_or_create(branch=branch, block=block, number=number,
                                           defaults={"capacity": capacity, "room_type": kind, "floor": int(number[0]) - 1})
        HostelFeeRule.objects.get_or_create(branch=branch, block=None, room_type="", defaults={"monthly_amount": 2500})

        mess, created = Mess.objects.get_or_create(
            branch=branch, name="Central mess",
            defaults={"name_hi": "केंद्रीय मेस", "contractor_name": "Annapurna Caterers", "contractor_phone": "9800099000",
                      "monthly_charge": 3000, "per_day_rate": 110, "rebate_min_days": 5, "rebate_per_day": 90,
                      "guest_meal_rate": 60},
        )
        if created:
            mess.blocks.set([boys, girls])
            for meal, rate in [("breakfast", 25), ("lunch", 45), ("snacks", 15), ("dinner", 45)]:
                MessMealRate.objects.create(mess=mess, meal=meal, rate=rate)
            week = [
                ("Poha, tea", "Rice, dal, aloo gobhi, roti", "Samosa, tea", "Roti, rajma, rice"),
                ("Idli, sambar", "Rice, dal, bhindi, roti", "Biscuits, tea", "Roti, chicken curry, rice"),
                ("Paratha, curd", "Rice, kadhi, roti, salad", "Chana chaat", "Roti, paneer, rice"),
                ("Upma, tea", "Rice, dal, lauki, roti", "Pakora, tea", "Roti, egg curry, rice"),
                ("Chura, dahi", "Rice, dal, aloo bhujia, roti", "Bread, tea", "Roti, mix veg, rice"),
                ("Puri, sabzi", "Khichdi, papad, chokha", "Litti, tea", "Roti, fish curry, rice"),
                ("Aloo paratha", "Veg biryani, raita", "Jalebi", "Roti, dal makhani, kheer"),
            ]
            for day, meals in enumerate(week):
                for meal, items in zip(("breakfast", "lunch", "snacks", "dinner"), meals):
                    nonveg = any(w in items for w in ("chicken", "egg", "fish"))
                    MenuItem.objects.create(branch=branch, mess=mess, day=day, meal=meal, items=items, is_veg=not nonveg)

        for adm, block in ((f"{branch.code.upper()}-C7-001", boys), (f"{branch.code.upper()}-C7-002", girls)):
            student = Student.objects.filter(branch=branch, admission_no=adm).first()
            if student and not student.hostel_allocations.exists():
                services.allocate(student=student, room=Room.objects.get(block=block, number="101"))
