"""Staging only: drive every active vehicle of a tenant along its route (ADR-005 simulated GPS).

    python manage.py simulate_gps --schema pqr --steps 40 --interval 5
"""
import time

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.transport.gps import simulate_step
from apps.transport.models import Vehicle


class Command(BaseCommand):
    help = "Simulate GPS positions along each vehicle's route (staging)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True)
        parser.add_argument("--steps", type=int, default=40)
        parser.add_argument("--interval", type=float, default=5.0, help="Seconds between steps")

    def handle(self, *args, schema, steps, interval, **kw):
        with schema_context(schema):
            vehicles = list(Vehicle.objects.filter(is_active=True, route__isnull=False))
            for n in range(steps + 1):
                for v in vehicles:
                    simulate_step(v, n / steps, speed=25 + (n % 5) * 4)
                self.stdout.write(f"step {n}/{steps}: {len(vehicles)} vehicles")
                if n < steps:
                    time.sleep(interval)
