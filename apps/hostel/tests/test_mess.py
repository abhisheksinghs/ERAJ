"""Mess acceptance scenarios (scope doc, Mess). Real tenant schema.

    python manage.py test apps.hostel.tests.test_mess
"""
from datetime import date
from decimal import Decimal

from freezegun import freeze_time

from apps.core.testing import EraTestCase
from apps.fees.models import Charge
from apps.hostel import mess, services
from apps.hostel.models import Block, MealCount, MenuItem, Mess, MessMealRate, MessMember, MessRebate, Room

D = Decimal


class MessBase(EraTestCase):
    def setUp(self):
        super().setUp()
        self.block = Block.objects.create(branch=self.branch, code="A", name="Block A")
        self.room = Room.objects.create(branch=self.branch, block=self.block, number="101", capacity=4)
        self.mess = Mess.objects.create(
            branch=self.branch, name="Central", contractor_name="Annapurna", monthly_charge=D("3100"),
            per_day_rate=D("110"), rebate_min_days=5, rebate_per_day=D("90"), guest_meal_rate=D("60"),
        )
        self.mess.blocks.add(self.block)
        for meal, rate in [("breakfast", 25), ("lunch", 45), ("snacks", 15), ("dinner", 45)]:
            MessMealRate.objects.create(mess=self.mess, meal=meal, rate=D(rate))

    def member(self, plan="monthly", start=date(2026, 10, 1)):
        return mess.enrol(mess=self.mess, student=self.make_student(), plan=plan, start=start)

    def mess_charges(self, student):
        return Charge.objects.filter(student=student, source_type=Charge.Source.MESS, cancelled_at__isnull=True)


class EnrolmentAndBillingTest(MessBase):
    @freeze_time("2026-10-01")
    def test_allocation_enrols_in_block_mess_and_bills_the_month(self):
        s = self.make_student()
        alloc = services.allocate(student=s, room=self.room)
        m = MessMember.objects.get(student=s)
        self.assertEqual((m.mess, m.plan, m.allocation), (self.mess, "monthly", alloc))
        self.assertEqual([c.amount for c in self.mess_charges(s)], [D("3100.00")])

    def test_vacating_ends_mess_membership(self):
        s = self.make_student()
        with freeze_time("2026-10-01"):
            alloc = services.allocate(student=s, room=self.room)
        with freeze_time("2026-10-20"):
            services.vacate(allocation=alloc)
        self.assertEqual(MessMember.objects.get(student=s).end_date, date(2026, 10, 20))
        with freeze_time("2026-11-01"):
            mess.bill_mess_month(branch=self.branch)
        self.assertEqual(self.mess_charges(s).count(), 1)  # no November charge

    def test_rebate_only_for_leave_of_minimum_length(self):
        with freeze_time("2026-10-01"):
            long_leave, short_leave = self.member(), self.member()
        mess.record_leave(member=long_leave, from_date=date(2026, 10, 5), to_date=date(2026, 10, 11))  # 7 days
        mess.record_leave(member=short_leave, from_date=date(2026, 10, 5), to_date=date(2026, 10, 7))  # 3 days
        with freeze_time("2026-11-01"):
            mess.bill_mess_month(branch=self.branch)
        nov = lambda m: self.mess_charges(m.student).get(source_id__endswith="2026-11")  # noqa: E731
        self.assertEqual(nov(long_leave).amount, D("3100") - 7 * D("90"))
        self.assertEqual(nov(short_leave).amount, D("3100.00"))
        rebate = MessRebate.objects.get()
        self.assertEqual((rebate.member, rebate.days, rebate.amount), (long_leave, 7, D("630.00")))

    def test_monthly_and_per_day_members_with_ten_days_leave(self):
        with freeze_time("2026-10-01"):
            monthly, per_day = self.member("monthly"), self.member("per_day")
        for m in (monthly, per_day):
            mess.record_leave(member=m, from_date=date(2026, 10, 11), to_date=date(2026, 10, 20))
        with freeze_time("2026-11-01"):
            mess.bill_mess_month(branch=self.branch)
            mess.bill_mess_month(branch=self.branch)  # re-run is harmless
        # monthly: full October in advance, 10-day rebate on November's charge
        self.assertEqual(
            sorted(c.amount for c in self.mess_charges(monthly.student)), [D("3100") - 10 * D("90"), D("3100.00")]
        )
        # per-day: October in arrears, 31 − 10 = 21 days
        self.assertEqual([c.amount for c in self.mess_charges(per_day.student)], [21 * D("110")])

    def test_two_guest_meals_are_charged(self):
        with freeze_time("2026-10-01"):
            m = self.member()
        mess.add_guest_meal(member=m, meal="lunch", on=date(2026, 10, 3), guest_name="Uncle")
        mess.add_guest_meal(member=m, meal="dinner", on=date(2026, 10, 3))
        guest = Charge.objects.filter(student=m.student, source_type=Charge.Source.GUEST_MEAL)
        self.assertEqual(sorted(c.amount for c in guest), [D("60.00"), D("60.00")])

    def test_staff_member_is_counted_but_not_billed(self):
        m = mess.enrol(mess=self.mess, staff=self.make_staff(), start=date(2026, 10, 1))
        self.assertFalse(Charge.objects.exists())
        self.assertEqual(mess.headcount(self.mess, date(2026, 10, 2))["enrolled"], 1)
        self.assertIsNone(m.student)


class HeadcountAndContractorTest(MessBase):
    def test_tomorrow_lunch_is_enrolled_minus_on_leave(self):
        with freeze_time("2026-10-01"):
            members = [self.member() for _ in range(5)]
        mess.record_leave(member=members[0], from_date=date(2026, 10, 9), to_date=date(2026, 10, 12))
        mess.record_leave(member=members[1], from_date=date(2026, 10, 10), to_date=date(2026, 10, 10))
        mess.add_guest_meal(member=members[2], meal="lunch", on=date(2026, 10, 10), count=2)
        lunch = next(x for x in mess.headcount(self.mess, date(2026, 10, 10))["meals"] if x["meal"] == "lunch")
        self.assertEqual((lunch["members"], lunch["guests"], lunch["expected"]), (3, 2, 5))

    def test_contractor_bill_is_plates_times_rates(self):
        with freeze_time("2026-10-01"):
            self.member(), self.member()
        # warden recorded every lunch and dinner; breakfast/snacks fall back to the expected count
        for day in range(1, 32):
            MealCount.objects.create(branch=self.branch, mess=self.mess, date=date(2026, 10, day), meal="lunch", served=2)
            MealCount.objects.create(branch=self.branch, mess=self.mess, date=date(2026, 10, day), meal="dinner", served=1)
        bill = mess.contractor_bill(self.mess, date(2026, 10, 1))
        rows = {r["meal"]: r for r in bill["rows"]}
        self.assertEqual(rows["lunch"]["plates"], 62)
        self.assertEqual(rows["dinner"]["plates"], 31)
        self.assertEqual(rows["breakfast"]["plates"], 62)
        self.assertEqual(rows["breakfast"]["estimated_days"], 31)
        expected = 62 * D("45") + 31 * D("45") + 62 * D("25") + 62 * D("15")
        self.assertEqual(bill["total"], expected)

    def test_week_menu_prints_on_one_page(self):
        from apps.hostel.pdf import menu_document

        for day in range(7):
            for meal in ("breakfast", "lunch", "snacks", "dinner"):
                MenuItem.objects.create(branch=self.branch, mess=self.mess, day=day, meal=meal,
                                        items="Rice, dal, seasonal sabzi, roti, salad", is_veg=day != 3)
        self.assertEqual(len(menu_document(self.mess).pages), 1)
        self.assertEqual(len(menu_document(self.mess, lang="hi").pages), 1)
        r = self.api(self.make_user("warden")).get(f"/api/hostel/messes/{self.mess.pk}/menu-pdf/")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
