"""Allocation workflow — capacity, one-room-per-resident, vacate + waitlist,
maintenance blocking. Real tenant schema.

    python manage.py test apps.hostel.tests.test_allocation
"""
from django_tenants.test.cases import TenantTestCase

from apps.core.exceptions import Conflict
from apps.hostel import services
from apps.hostel.models import MaintenanceTicket, Resident, Room, Waitlist


class AllocationTest(TenantTestCase):
    def setUp(self):
        self.room = Room.objects.create(number="101", capacity=1)
        self.r1 = Resident.objects.create(full_name="R1")
        self.r2 = Resident.objects.create(full_name="R2")

    def test_allocate_respects_capacity(self):
        services.allocate(resident=self.r1, room=self.room)
        with self.assertRaises(Conflict):
            services.allocate(resident=self.r2, room=self.room)

    def test_one_active_allocation_per_resident(self):
        room2 = Room.objects.create(number="102", capacity=2)
        services.allocate(resident=self.r1, room=self.room)
        with self.assertRaises(Conflict):
            services.allocate(resident=self.r1, room=room2)

    def test_vacate_frees_bed_and_offers_waitlist(self):
        alloc = services.allocate(resident=self.r1, room=self.room)
        entry = Waitlist.objects.create(resident=self.r2, room=self.room)
        services.vacate(allocation=alloc)
        entry.refresh_from_db()
        self.assertEqual(entry.status, Waitlist.Status.OFFERED)
        self.assertEqual(self.room.available_beds, 1)

    def test_open_maintenance_ticket_blocks_allocation(self):
        MaintenanceTicket.objects.create(room=self.room, summary="leak")
        with self.assertRaises(Conflict):
            services.allocate(resident=self.r1, room=self.room)

    def test_room_under_maintenance_blocks_allocation(self):
        self.room.status = Room.Status.MAINTENANCE
        self.room.save()
        with self.assertRaises(Conflict):
            services.allocate(resident=self.r1, room=self.room)
