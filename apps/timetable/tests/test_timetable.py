"""Timetable and substitution acceptance scenarios. Real tenant schema.

    python manage.py test apps.timetable.tests.test_timetable
"""
from datetime import date, time

from apps.core.exceptions import Conflict
from apps.core.testing import EraTestCase
from apps.people.models import Program, Section, Subject, TeachingAssignment
from apps.timetable import services
from apps.timetable.models import BellSchedule, PeriodSlot, Room, Substitution, TeacherAbsence, TeacherLoad, TimetableEntry

MON = date(2026, 10, 26)  # a Monday


class TimetableBase(EraTestCase):
    def setUp(self):
        super().setUp()
        self.p6 = Program.objects.create(branch=self.branch, code="C6", name="Class 6")
        self.p7 = Program.objects.create(branch=self.branch, code="C7", name="Class 7")
        self.s6 = Section.objects.create(branch=self.branch, academic_year=self.year, program=self.p6, name="A")
        self.s7 = Section.objects.create(branch=self.branch, academic_year=self.year, program=self.p7, name="A")
        self.junior = BellSchedule.objects.create(branch=self.branch, name="Main", is_default=True)
        times = [(1, "08:00", "08:40"), (2, "08:40", "09:20"), (3, "09:20", "10:00"), (4, "10:00", "10:20"),
                 (5, "10:20", "11:00"), (6, "11:00", "11:40"), (7, "11:40", "12:20")]
        self.slots = {}
        for n, a, b in times:
            self.slots[n] = PeriodSlot.objects.create(schedule=self.junior, number=n, label="Break" if n == 4 else f"Period {n}",
                                                      start=time.fromisoformat(a), end=time.fromisoformat(b), is_break=n == 4)
        self.teachers = [self.make_staff(full_name=name) for name in ["Anita Maths", "Bimal Maths", "Chanda Hindi", "Dev Science"]]
        self.subjects = {}
        for prog in (self.p6, self.p7):
            for name in ("Maths", "Hindi", "Science"):
                self.subjects[(prog.code, name)] = Subject.objects.create(branch=self.branch, code=f"{prog.code}-{name[:3]}", name=name, program=prog)

    def assign(self, staff, section, subject_name, periods=0):
        subj = self.subjects[(section.program.code, subject_name)]
        return TeachingAssignment.objects.create(branch=self.branch, staff=staff, subject=subj, section=section, periods_per_week=periods)


class BuilderTest(TimetableBase):
    def test_build_a_week_and_refuse_a_double_booked_teacher(self):
        anita = self.teachers[0]
        a6 = self.assign(anita, self.s6, "Maths")
        a7 = self.assign(anita, self.s7, "Maths")
        for day in range(6):
            services.place(section=self.s6, day=day, slot=self.slots[1], assignment=a6)
        self.assertEqual(TimetableEntry.objects.filter(section=self.s6).count(), 6)
        with self.assertRaisesMessage(Conflict, "Anita Maths already teaches Class 6-A in Period 1"):
            services.place(section=self.s7, day=0, slot=self.slots[1], assignment=a7)
        services.place(section=self.s7, day=0, slot=self.slots[2], assignment=a7)  # next period is fine

    def test_overlap_across_bell_schedules_is_a_clash(self):
        anita = self.teachers[0]
        senior = BellSchedule.objects.create(branch=self.branch, name="Senior wing")
        senior.sections.add(self.s7)
        odd = PeriodSlot.objects.create(schedule=senior, number=1, label="Period 1", start=time(8, 20), end=time(9, 0))
        services.place(section=self.s6, day=0, slot=self.slots[1], assignment=self.assign(anita, self.s6, "Maths"))
        with self.assertRaises(Conflict):  # 08:20–09:00 overlaps 08:00–08:40
            services.place(section=self.s7, day=0, slot=odd, assignment=self.assign(anita, self.s7, "Maths"))
        with self.assertRaisesMessage(Conflict, "not on this section's bell schedule"):
            services.place(section=self.s7, day=0, slot=self.slots[2], assignment=TeachingAssignment.objects.get(section=self.s7))

    def test_section_slot_break_room_weekly_limits(self):
        anita, bimal = self.teachers[:2]
        a = self.assign(anita, self.s6, "Maths", periods=2)
        b = self.assign(bimal, self.s7, "Maths")
        lab = Room.objects.create(branch=self.branch, name="Lab 1")
        services.place(section=self.s6, day=0, slot=self.slots[1], assignment=a, room=lab)
        with self.assertRaisesMessage(Conflict, "already has Maths"):
            services.place(section=self.s6, day=0, slot=self.slots[1], assignment=self.assign(self.teachers[2], self.s6, "Hindi"))
        with self.assertRaisesMessage(Conflict, "break"):
            services.place(section=self.s6, day=0, slot=self.slots[4], assignment=a)
        with self.assertRaisesMessage(Conflict, "Lab 1 is booked"):
            services.place(section=self.s7, day=0, slot=self.slots[1], assignment=b, room=lab)
        services.place(section=self.s6, day=1, slot=self.slots[1], assignment=a)
        with self.assertRaisesMessage(Conflict, "already has its 2 periods"):
            services.place(section=self.s6, day=2, slot=self.slots[1], assignment=a)
        TeacherLoad.objects.create(branch=self.branch, staff=bimal, max_periods_per_week=1)
        services.place(section=self.s7, day=1, slot=self.slots[2], assignment=b)
        with self.assertRaisesMessage(Conflict, "limit 1"):
            services.place(section=self.s7, day=2, slot=self.slots[2], assignment=b)

    def test_api_refuses_clash_and_teacher_cannot_edit(self):
        anita = self.teachers[0]
        a6, a7 = self.assign(anita, self.s6, "Maths"), self.assign(anita, self.s7, "Maths")
        admin = self.api(self.make_user("admin"))
        body = {"section": self.s6.pk, "day": 0, "slot": self.slots[1].pk, "assignment": a6.pk}
        self.assertEqual(admin.post("/api/timetable/entries/", body, content_type="application/json").status_code, 201)
        r = admin.post("/api/timetable/entries/", {**body, "section": self.s7.pk, "assignment": a7.pk}, content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertIn("already teaches", r.json()["detail"])
        r = self.api(self.make_user("teacher")).post("/api/timetable/entries/", {**body, "slot": self.slots[2].pk}, content_type="application/json")
        self.assertEqual(r.status_code, 403)
        grid = admin.get(f"/api/timetable/views/section/?section={self.s6.pk}").json()
        self.assertEqual([c["subject"] for c in grid["cells"]], ["Maths"])


class SubstitutionTest(TimetableBase):
    def setUp(self):
        super().setUp()
        self.anita, self.bimal, self.chanda, self.dev = self.teachers
        a6 = self.assign(self.anita, self.s6, "Maths")
        a7 = self.assign(self.anita, self.s7, "Maths")
        self.assign(self.bimal, self.s7, "Maths")      # same subject, Class 7
        h6 = self.assign(self.chanda, self.s6, "Hindi")
        sc7 = self.assign(self.dev, self.s7, "Science")
        # Anita teaches 5 periods on Monday
        for n, sec, asg in [(1, self.s6, a6), (2, self.s7, a7), (3, self.s6, a6), (5, self.s7, a7), (6, self.s6, a6)]:
            services.place(section=sec, day=0, slot=self.slots[n], assignment=asg)
        services.place(section=self.s6, day=0, slot=self.slots[2], assignment=h6)   # Chanda busy in P2
        services.place(section=self.s7, day=0, slot=self.slots[1], assignment=sc7)  # Dev busy in P1

    def test_absent_teachers_five_periods_listed_suggested_and_covered(self):
        TeacherAbsence.objects.create(branch=self.branch, staff=self.anita, date=MON, reason="Casual leave")
        periods = services.periods_to_cover(branch=self.branch, on=MON)
        self.assertEqual(len(periods), 5)
        for p in periods:
            entry = TimetableEntry.objects.get(pk=p["entry"])
            options = services.suggest(entry=entry, on=MON)
            self.assertNotIn(self.anita.pk, [o["staff"] for o in options])
            self.assertEqual(options[0]["staff"], self.bimal.pk)  # same subject first
            if entry.slot.number == 1:
                self.assertNotIn(self.dev.pk, [o["staff"] for o in options])   # busy in P1
            if entry.slot.number == 2:
                self.assertNotIn(self.chanda.pk, [o["staff"] for o in options])  # busy in P2
            services.confirm(entry=entry, on=MON, substitute=self.bimal, by="office")
        self.assertEqual(Substitution.objects.filter(date=MON).count(), 5)
        self.assertTrue(all(p["substitute"] == self.bimal.pk for p in services.periods_to_cover(branch=self.branch, on=MON)))

        grid = services.teacher_grid(self.bimal, MON)
        self.assertEqual(sum(1 for s in grid["substitutions"] if s["covering_for"] == "Anita Maths"), 5)
        sec = services.section_grid(self.s6, MON)
        self.assertEqual({c["substitute_name"] for c in sec["cells"] if c["teacher_name"] == "Anita Maths"}, {"Bimal Maths"})

    def test_busy_or_absent_substitute_is_refused(self):
        TeacherAbsence.objects.create(branch=self.branch, staff=self.anita, date=MON)
        p1 = TimetableEntry.objects.get(section=self.s6, day=0, slot=self.slots[1])
        with self.assertRaisesMessage(Conflict, "not free"):
            services.confirm(entry=p1, on=MON, substitute=self.dev, by="office")  # teaching 7-A in P1
        services.confirm(entry=p1, on=MON, substitute=self.bimal, by="office")
        p1_7 = TimetableEntry.objects.get(section=self.s7, day=0, slot=self.slots[2])
        services.confirm(entry=p1_7, on=MON, substitute=self.bimal, by="office")
        p3 = TimetableEntry.objects.get(section=self.s6, day=0, slot=self.slots[3])
        TeacherAbsence.objects.create(branch=self.branch, staff=self.chanda, date=MON)
        self.assertNotIn(self.chanda.pk, [o["staff"] for o in services.suggest(entry=p3, on=MON)])

    def test_print_teacher_timetable_and_month_register(self):
        TeacherAbsence.objects.create(branch=self.branch, staff=self.anita, date=MON)
        for p in services.periods_to_cover(branch=self.branch, on=MON):
            services.confirm(entry=TimetableEntry.objects.get(pk=p["entry"]), on=MON, substitute=self.bimal, by="office")
        admin = self.api(self.make_user("admin"))
        r = admin.get(f"/api/timetable/views/teacher/?staff={self.anita.pk}&pdf=1")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
        reg = admin.get("/api/timetable/substitutions/register/?month=2026-10").json()
        self.assertEqual(reg["per_teacher"], [{"staff": self.bimal.pk, "name": "Bimal Maths", "periods": 5}])
        r = admin.get("/api/timetable/substitutions/register/?month=2026-10&pdf=1")
        self.assertEqual(r["Content-Type"], "application/pdf")
        cover = admin.get(f"/api/timetable/substitutions/to-cover/?date={MON}").json()
        self.assertEqual(len(cover["periods"]), 5)
