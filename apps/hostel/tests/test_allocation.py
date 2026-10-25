"""Hostel acceptance scenarios (scope doc, Hostel and Mess) — rooms, waiting
list, repairs, hostel fees. Real tenant schema.

    python manage.py test apps.hostel.tests.test_allocation
"""
from datetime import date
from decimal import Decimal

from freezegun import freeze_time

from apps.core.exceptions import Conflict
from apps.core.testing import EraTestCase
from apps.fees.models import Charge
from apps.fees.selectors import charges_with_balance
from apps.hostel import services
from apps.hostel.models import Block, HostelFeeRule, MaintenanceTicket, Room, Waitlist


class HostelBase(EraTestCase):
    def setUp(self):
        super().setUp()
        self.block_a = Block.objects.create(branch=self.branch, code="A", name="Block A")
        self.block_b = Block.objects.create(branch=self.branch, code="B", name="Block B")
        for block in (self.block_a, self.block_b):
            for n in range(1, 6):
                Room.objects.create(branch=self.branch, block=block, number=f"10{n}", capacity=2)
        self.room = Room.objects.get(block=self.block_a, number="101")


class AllocationTest(HostelBase):
    def test_two_blocks_ten_rooms_full_room_refuses_next(self):
        self.assertEqual(Room.objects.count(), 10)
        services.allocate(student=self.make_student(), room=self.room)
        services.allocate(student=self.make_student(), room=self.room)
        with self.assertRaisesMessage(Conflict, "full"):
            services.allocate(student=self.make_student(), room=self.room)

    def test_one_bed_per_student(self):
        s = self.make_student()
        services.allocate(student=s, room=self.room)
        with self.assertRaises(Conflict):
            services.allocate(student=s, room=Room.objects.get(block=self.block_b, number="101"))

    def test_waitlisted_student_is_offered_the_freed_bed(self):
        first = services.allocate(student=self.make_student(), room=self.room)
        services.allocate(student=self.make_student(), room=self.room)
        waiting = services.add_to_waitlist(student=self.make_student(), room=self.room)
        services.vacate(allocation=first)
        waiting.refresh_from_db()
        self.assertEqual(waiting.status, Waitlist.Status.OFFERED)
        first.refresh_from_db()
        self.assertIsNotNone(first.check_out_date)  # stay kept in history
        services.allocate(student=waiting.student, room=self.room)
        waiting.refresh_from_db()
        self.assertEqual(waiting.status, Waitlist.Status.FULFILLED)

    def test_open_repair_blocks_allocation_until_closed(self):
        ticket = services.open_ticket(room=self.room, summary="Broken window")
        with self.assertRaisesMessage(Conflict, "repair"):
            services.allocate(student=self.make_student(), room=self.room)
        services.close_ticket(ticket=ticket, action_taken="Glass replaced")
        self.assertEqual(ticket.status, MaintenanceTicket.Status.CLOSED)
        services.allocate(student=self.make_student(), room=self.room)

    def test_closed_room_and_gender_rule(self):
        self.room.status = Room.Status.CLOSED
        self.room.save()
        with self.assertRaises(Conflict):
            services.allocate(student=self.make_student(), room=self.room)
        girls = Block.objects.create(branch=self.branch, code="G", name="Girls", gender="female")
        g_room = Room.objects.create(branch=self.branch, block=girls, number="1", capacity=2)
        with self.assertRaisesMessage(Conflict, "girls"):
            services.allocate(student=self.make_student(gender="male"), room=g_room)
        services.allocate(student=self.make_student(gender="female"), room=g_room)

    def test_board_shows_residents_and_free_beds(self):
        s = self.make_student()
        services.allocate(student=s, room=self.room)
        rows = self.api(self.make_user("warden")).get(f"/api/hostel/rooms/board/?block={self.block_a.pk}").json()
        row = next(r for r in rows if r["id"] == self.room.pk)
        self.assertEqual((row["free"], [r["student"] for r in row["residents"]]), (1, [s.pk]))
        self.assertEqual(len(rows), 5)


class HostelFeeTest(HostelBase):
    def setUp(self):
        super().setUp()
        HostelFeeRule.objects.create(branch=self.branch, monthly_amount=Decimal("2500"))
        HostelFeeRule.objects.create(branch=self.branch, block=self.block_a, monthly_amount=Decimal("3000"))

    @freeze_time("2026-10-05")
    def test_allocation_puts_hostel_fee_on_fees_account(self):
        s = self.make_student()
        services.allocate(student=s, room=self.room)
        charges = Charge.objects.filter(student=s, source_type=Charge.Source.HOSTEL).order_by("due_date")
        self.assertEqual(charges.count(), 6)  # Oct 2026 .. Mar 2027 (academic year end)
        self.assertEqual({c.amount for c in charges}, {Decimal("3000.00")})  # block rule beats branch rule
        self.assertEqual(charges.first().due_date, date(2026, 10, 10))

    def test_vacating_stops_future_instalments_only(self):
        s = self.make_student()
        with freeze_time("2026-10-05"):
            alloc = services.allocate(student=s, room=Room.objects.get(block=self.block_b, number="101"))
        with freeze_time("2026-12-20"):
            services.vacate(allocation=alloc, reason="Left college")
        live = charges_with_balance(Charge.objects.filter(student=s, source_type=Charge.Source.HOSTEL))
        self.assertEqual(sorted(c.due_date.month for c in live), [10, 11, 12])
        self.assertEqual({c.amount for c in live}, {Decimal("2500.00")})

    def test_warden_api_allocates_and_accountant_cannot(self):
        s = self.make_student()
        r = self.api(self.make_user("accountant")).post(
            "/api/hostel/allocations/", {"student": s.pk, "room": self.room.pk}, content_type="application/json"
        )
        self.assertEqual(r.status_code, 403)
        r = self.api(self.make_user("warden")).post(
            "/api/hostel/allocations/", {"student": s.pk, "room": self.room.pk}, content_type="application/json"
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["room_label"], "A-101")
