"""Transport acceptance scenarios (scope doc, Transport 1–6) and guards. Real tenant schema.

    python manage.py test apps.transport.tests.test_transport
"""
import json
from datetime import date, time
from decimal import Decimal

from django_tenants.utils import schema_context
from freezegun import freeze_time

from apps.core.exceptions import Conflict
from apps.core.models import AuditLog
from apps.core.testing import EraTestCase
from apps.fees.models import Charge
from apps.people.models import Guardian, StudentGuardian
from apps.transport import services
from apps.transport.models import FareSlab, Route, RouteStop, TransportAlert, TransportAssignment, Vehicle, VehicleDocument

D = Decimal
# Five stops heading north from the campus (≈ 1.1 km apart)
STOPS = [("Gandhi Maidan", "25.610000", "85.140000", "1.0", "700"), ("Boring Road", "25.620000", "85.140000", "2.1", "800"),
         ("Patliputra", "25.630000", "85.140000", "3.2", "900"), ("Rajiv Nagar", "25.640000", "85.140000", "4.4", None),
         ("Danapur", "25.650000", "85.140000", "6.0", None)]


@freeze_time("2026-11-20 10:00:00+05:30")
class TransportBase(EraTestCase):
    def setUp(self):
        super().setUp()
        self.route = Route.objects.create(branch=self.branch, code="R1", name="North line")
        self.stops = []
        for i, (name, lat, lng, km, fare) in enumerate(STOPS, start=1):
            self.stops.append(RouteStop.objects.create(
                branch=self.branch, route=self.route, sequence=i, name=name, latitude=D(lat), longitude=D(lng),
                distance_km=D(km), monthly_fare=D(fare) if fare else None, pickup_time=time(7, 0 + i * 5)))
        FareSlab.objects.create(branch=self.branch, from_km=D("4"), to_km=D("10"), monthly_fare=D("1100"))
        self.bus = Vehicle.objects.create(branch=self.branch, registration_no="BR01PA1234", capacity=40, route=self.route,
                                          driver_name="Ramesh", driver_phone="9800000001")
        self.tr = self.api(self.make_user("transport"))

    def student(self, n=None, phone="9811100000"):
        s = self.make_student()
        g = Guardian.objects.create(branch=self.branch, full_name=f"Parent of {s.full_name}", phone=phone)
        StudentGuardian.objects.create(branch=self.branch, student=s, guardian=g, relation="father", is_primary=True)
        return s

    def post(self, client, url, body=None):
        return client.post(url, body or {}, content_type="application/json")

    def live_charges(self, student):
        return list(Charge.objects.filter(student=student, source_type="transport", cancelled_at__isnull=True)
                    .order_by("due_date").values_list("due_date", "amount"))


class Scenario1Test(TransportBase):
    def test_scenario_transport_1_forty_seats_forty_first_refused(self):
        r = self.post(self.tr, "/api/transport/routes/", {"code": "R2", "name": "East line", "stops": [
            {"sequence": i, "name": f"Stop {i}", "monthly_fare": "500"} for i in range(1, 6)]})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["stop_count"], 5)
        for _ in range(40):
            services.assign(stop=self.stops[0], vehicle=self.bus, start=date(2026, 11, 20), student=self.student())
        r = self.post(self.tr, "/api/transport/assignments/", {"student": self.student().pk, "stop": self.stops[1].pk,
                                                                "vehicle": self.bus.pk, "start_date": "2026-11-20"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("full (40 of 40 seats)", r.json()["detail"])
        occ = self.tr.get("/api/transport/reports/occupancy/").json()
        self.assertEqual(occ[0]["riders"], 40)

    def test_seat_freed_by_a_rider_leaving_counts_only_after_they_leave(self):
        bus = Vehicle.objects.create(branch=self.branch, registration_no="BR01VAN1", capacity=1, route=self.route)
        a = services.assign(stop=self.stops[0], vehicle=bus, start=date(2026, 11, 20), student=self.student())
        services.stop(assignment=a, from_date=date(2026, 12, 1))
        with self.assertRaisesMessage(Conflict, "full"):
            services.assign(stop=self.stops[0], vehicle=bus, start=date(2026, 11, 25), student=self.student())
        services.assign(stop=self.stops[0], vehicle=bus, start=date(2026, 12, 1), student=self.student())


class Scenario2and3Test(TransportBase):
    def test_scenario_transport_2_stop_fare_posts_to_fees(self):
        s = self.student()
        r = self.post(self.tr, "/api/transport/assignments/", {"student": s.pk, "stop": self.stops[2].pk,
                                                                "vehicle": self.bus.pk, "start_date": "2026-11-20"})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["monthly_fare"], "900.00")
        # November (due on joining day) to March, ₹900 each
        self.assertEqual(self.live_charges(s), [(date(2026, 11, 20), D("900")), (date(2026, 12, 10), D("900")),
                                                (date(2027, 1, 10), D("900")), (date(2027, 2, 10), D("900")),
                                                (date(2027, 3, 10), D("900"))])
        # stop 4 has no own fare: the 4–10 km slab applies
        s2 = self.student()
        a = services.assign(stop=self.stops[3], vehicle=self.bus, start=date(2026, 11, 20), student=s2)
        self.assertEqual(a.monthly_fare, D("1100"))
        # the accountant sees it on the student's account
        acct = self.api(self.make_user("accountant"))
        dues = acct.get(f"/api/fees/charges/?student={s.pk}").json()
        self.assertEqual(dues["count"], 5)

    def test_scenario_transport_3_stop_from_next_month_stops_that_months_fee(self):
        s = self.student()
        a = services.assign(stop=self.stops[2], vehicle=self.bus, start=date(2026, 11, 20), student=s)
        r = self.post(self.tr, f"/api/transport/assignments/{a.pk}/stop/", {"from_date": "2026-12-01"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["end_date"], "2026-11-30")
        self.assertEqual(self.live_charges(s), [(date(2026, 11, 20), D("900"))])
        self.assertNotIn(a.pk, [x["id"] for x in self.tr.get("/api/transport/assignments/?riding=true").json()["results"]
                                if x["end_date"] is None])

    def test_mid_month_stop_keeps_that_month_and_change_of_stop_reprices(self):
        s = self.student()
        a = services.assign(stop=self.stops[2], vehicle=self.bus, start=date(2026, 11, 20), student=s)
        services.stop(assignment=a, from_date=date(2027, 1, 15))
        self.assertEqual(len(self.live_charges(s)), 3)  # Nov, Dec, Jan
        s2 = self.student()
        b = services.assign(stop=self.stops[0], vehicle=self.bus, start=date(2026, 11, 20), student=s2)
        r = self.post(self.tr, f"/api/transport/assignments/{b.pk}/change/",
                      {"stop": self.stops[4].pk, "vehicle": self.bus.pk, "from_date": "2026-12-01"})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.live_charges(s2), [(date(2026, 11, 20), D("700")), (date(2026, 12, 10), D("1100")),
                                                 (date(2027, 1, 10), D("1100")), (date(2027, 2, 10), D("1100")),
                                                 (date(2027, 3, 10), D("1100"))])

    def test_staff_ride_free_and_a_rider_cannot_be_on_two_buses(self):
        t = self.make_staff()
        a = services.assign(stop=self.stops[1], vehicle=self.bus, start=date(2026, 11, 20), staff=t)
        self.assertEqual(a.monthly_fare, 0)
        with self.assertRaisesMessage(Conflict, "already rides"):
            services.assign(stop=self.stops[2], vehicle=self.bus, start=date(2026, 11, 21), staff=t)
        RouteStop.objects.filter(pk=self.stops[4].pk).update(distance_km=D("12"))
        with self.assertRaisesMessage(Conflict, "No fare for stop Danapur"):
            services.assign(stop=RouteStop.objects.get(pk=self.stops[4].pk), vehicle=self.bus, start=date(2026, 11, 20),
                            student=self.student())


class Scenario4and5Test(TransportBase):
    def test_scenario_transport_4_insurance_expiring_in_20_days_is_reported(self):
        r = self.post(self.tr, "/api/transport/documents/", {"vehicle": self.bus.pk, "kind": "insurance", "number": "INS-77",
                                                              "expires_on": "2026-12-10"})
        self.assertEqual(r.status_code, 201, r.content)
        VehicleDocument.objects.create(branch=self.branch, vehicle=self.bus, kind="permit", expires_on=date(2027, 6, 1))
        rows = self.tr.get("/api/transport/reports/expiring/?days=30").json()
        self.assertEqual([(x["document"], x["days_left"]) for x in rows], [("Insurance", 20)])
        self.assertEqual(services.remind_expiring(branch=self.branch), 1)
        self.assertEqual(services.remind_expiring(branch=self.branch), 0)  # once per document
        with schema_context("public"):
            self.assertTrue(AuditLog.objects.filter(action="notify.staff", detail__event="transport.document_expiring").exists())

    def test_scenario_transport_5_stop_wise_rider_list_prints(self):
        for stop, phone in ((self.stops[0], "9811111111"), (self.stops[2], "9822222222"), (self.stops[2], "9833333333")):
            services.assign(stop=stop, vehicle=self.bus, start=date(2026, 11, 20), student=self.student(phone=phone))
        services.assign(stop=self.stops[2], vehicle=self.bus, start=date(2026, 11, 20), staff=self.make_staff(phone="9844444444"))
        rows = self.tr.get(f"/api/transport/reports/riders/?route={self.route.pk}").json()
        self.assertEqual([(r["stop_no"], r["guardian_phone"]) for r in rows][:1], [(1, "9811111111")])
        self.assertEqual(sum(1 for r in rows if r["stop_no"] == 3), 3)
        pdf = self.tr.get(f"/api/transport/reports/riders/?route={self.route.pk}&pdf=1")
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        xlsx = self.tr.get(f"/api/transport/reports/riders/?route={self.route.pk}&format=xlsx")
        self.assertEqual(xlsx.status_code, 200)


class Scenario6Test(TransportBase):
    def push(self, key, body):
        from django_tenants.test.client import TenantClient

        return TenantClient(self.tenant).post("/api/transport/gps/push/", json.dumps(body), content_type="application/json",
                                              HTTP_X_DEVICE_KEY=key)

    def test_scenario_transport_6_live_position_and_bus_near_stop_alert(self):
        near = self.student(phone="9855555555")
        far = self.student(phone="9866666666")
        services.assign(stop=self.stops[2], vehicle=self.bus, start=date(2026, 11, 20), student=near)
        services.assign(stop=self.stops[4], vehicle=self.bus, start=date(2026, 11, 20), student=far)
        # ~1.1 km before Patliputra: no alert yet
        r = self.push(self.bus.gps_key, {"lat": 25.620, "lng": 85.140, "speed": 30, "time": "2026-11-20 09:59:40"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json(), {"stored": 1, "alerts": 1})  # Boring Road itself is a stop
        live = next(v for v in self.tr.get("/api/transport/reports/live/").json() if v["vehicle"] == self.bus.pk)
        self.assertLess(live["age_seconds"], 60)
        # ~330 m from Patliputra (500 m setting): its riders' parents are alerted, once
        self.push(self.bus.gps_key, {"positions": [{"lat": 25.627, "lng": 85.140, "speed": 28, "time": "2026-11-20 09:59:50"},
                                                   {"lat": 25.628, "lng": 85.140, "speed": 25, "time": "2026-11-20 09:59:55"}]})
        alert = TransportAlert.objects.get(kind="near_stop", stop=self.stops[2])
        self.assertEqual(alert.recipients, 1)
        with schema_context("public"):
            sent = list(AuditLog.objects.filter(action="notify.guardian", detail__event="transport.near_stop")
                        .values_list("detail__phone", flat=True))
        self.assertEqual(sent, ["9855555555"])
        trip = self.tr.get(f"/api/transport/vehicles/{self.bus.pk}/trip/?date=2026-11-20").json()
        self.assertEqual(len(trip), 3)

    def test_over_speed_bad_key_and_bad_payload(self):
        self.assertEqual(self.push("wrong", {"lat": 25.6, "lng": 85.1}).status_code, 403)
        self.assertEqual(self.push(self.bus.gps_key, {"lat": 95, "lng": 85.1}).status_code, 400)
        self.assertEqual(self.push(self.bus.gps_key, {"lng": 85.1}).status_code, 400)
        self.push(self.bus.gps_key, {"lat": 25.70, "lng": 85.20, "speed": 62, "time": "2026-11-20 09:59:00"})
        self.push(self.bus.gps_key, {"lat": 25.70, "lng": 85.21, "speed": 64, "time": "2026-11-20 09:59:30"})
        self.assertEqual(TransportAlert.objects.filter(kind="over_speed").count(), 1)  # once per 10 minutes
        key = self.bus.gps_key
        r = self.post(self.api(self.make_user("admin")), f"/api/transport/vehicles/{self.bus.pk}/rotate-key/")
        self.assertNotEqual(r.json()["gps_key"], key)
        self.assertEqual(self.push(key, {"lat": 25.6, "lng": 85.1}).status_code, 403)


class GuardsTest(TransportBase):
    def test_roles_branches_and_key_visibility(self):
        self.assertEqual(self.api(self.make_user("teacher")).get("/api/transport/vehicles/").status_code, 403)
        self.assertNotIn("gps_key", self.tr.get("/api/transport/vehicles/").json()["results"][0])
        self.assertIn("gps_key", self.tr.get(f"/api/transport/vehicles/{self.bus.pk}/").json())
        other = self.make_branch("east")
        s = self.make_student(branch=other)
        r = self.post(self.tr, "/api/transport/assignments/", {"student": s.pk, "stop": self.stops[0].pk,
                                                                "vehicle": self.bus.pk, "start_date": "2026-11-20"})
        self.assertEqual(r.status_code, 400)
        r = self.post(self.tr, "/api/transport/assignments/", {"student": self.student().pk, "stop": self.stops[0].pk,
                                                                "vehicle": Vehicle.objects.create(branch=self.branch,
                                                                                                  registration_no="X1").pk,
                                                                "start_date": "2026-11-20"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(TransportAssignment.objects.exists())
