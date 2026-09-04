"""python manage.py test apps.transport.tests.test_assignment"""
from django_tenants.test.cases import TenantTestCase

from apps.core.exceptions import Conflict
from apps.transport import services
from apps.transport.models import Vehicle


class AssignmentTest(TenantTestCase):
    def setUp(self):
        self.vehicle = Vehicle.objects.create(number="V1", capacity=1)

    def test_assign_respects_capacity(self):
        services.assign(vehicle=self.vehicle, rider_name="A")
        with self.assertRaises(Conflict):
            services.assign(vehicle=self.vehicle, rider_name="B")

    def test_unassign_frees_a_seat(self):
        a = services.assign(vehicle=self.vehicle, rider_name="A")
        services.unassign(assignment=a)
        services.assign(vehicle=self.vehicle, rider_name="B")  # must not raise
        self.assertEqual(self.vehicle.active_riders, 1)
