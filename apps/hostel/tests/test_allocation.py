"""Allocation workflow — capacity, one-room-per-student, vacate + waitlist,
maintenance blocking. Real tenant schema.

    python manage.py test apps.hostel.tests.test_allocation
"""
from apps.core.exceptions import Conflict
from apps.core.testing import EraTestCase
from apps.hostel import services
from apps.hostel.models import MaintenanceTicket, Room, Waitlist


class AllocationTest(EraTestCase):
    def setUp(self):
        super().setUp()
        self.room = Room.objects.create(branch=self.branch, number="101", capacity=1)
        self.r1 = self.make_student()
        self.r2 = self.make_student()

    def test_allocate_respects_capacity(self):
        services.allocate(student=self.r1, room=self.room)
        with self.assertRaises(Conflict):
            services.allocate(student=self.r2, room=self.room)

    def test_one_active_allocation_per_resident(self):
        room2 = Room.objects.create(branch=self.branch, number="102", capacity=2)
        services.allocate(student=self.r1, room=self.room)
        with self.assertRaises(Conflict):
            services.allocate(student=self.r1, room=room2)

    def test_vacate_frees_bed_and_offers_waitlist(self):
        alloc = services.allocate(student=self.r1, room=self.room)
        entry = Waitlist.objects.create(branch=self.branch, student=self.r2, room=self.room)
        services.vacate(allocation=alloc)
        entry.refresh_from_db()
        self.assertEqual(entry.status, Waitlist.Status.OFFERED)
        self.assertEqual(self.room.available_beds, 1)

    def test_open_maintenance_ticket_blocks_allocation(self):
        MaintenanceTicket.objects.create(branch=self.branch, room=self.room, summary="leak")
        with self.assertRaises(Conflict):
            services.allocate(student=self.r1, room=self.room)

    def test_room_under_maintenance_blocks_allocation(self):
        self.room.status = Room.Status.MAINTENANCE
        self.room.save()
        with self.assertRaises(Conflict):
            services.allocate(student=self.r1, room=self.room)
