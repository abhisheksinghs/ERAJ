"""python manage.py test apps.attendance.tests.test_attendance"""
import datetime

from django_tenants.test.cases import TenantTestCase

from apps.attendance import services
from apps.attendance.models import AttendanceRecord, Student


class AttendanceTest(TenantTestCase):
    def setUp(self):
        self.student = Student.objects.create(full_name="A", roll_no="R1")

    def test_mark_is_idempotent_per_day(self):
        d = datetime.date(2026, 1, 1)
        services.mark(student=self.student, date=d, status=AttendanceRecord.Status.PRESENT)
        services.mark(student=self.student, date=d, status=AttendanceRecord.Status.ABSENT)
        self.assertEqual(AttendanceRecord.objects.filter(student=self.student, date=d).count(), 1)
        self.assertEqual(
            AttendanceRecord.objects.get(student=self.student, date=d).status,
            AttendanceRecord.Status.ABSENT,
        )

    def test_summary_percentage(self):
        for i, status in enumerate(
            [AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.ABSENT]
        ):
            services.mark(student=self.student, date=datetime.date(2026, 1, 1 + i), status=status)
        summary = services.summary(student=self.student)
        self.assertEqual(summary["total"], 3)
        self.assertAlmostEqual(summary["percentage"], 66.7, places=1)
