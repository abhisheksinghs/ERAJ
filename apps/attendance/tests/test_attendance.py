"""python manage.py test apps.attendance.tests.test_attendance"""
import datetime

from apps.attendance import services
from apps.attendance.models import AttendanceRecord
from apps.core.testing import EraTestCase


class AttendanceTest(EraTestCase):
    def setUp(self):
        super().setUp()
        self.student = self.make_student()

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

    def test_half_day_counts_half(self):
        services.mark(student=self.student, date=datetime.date(2026, 1, 1), status=AttendanceRecord.Status.HALF_DAY)
        services.mark(student=self.student, date=datetime.date(2026, 1, 2), status=AttendanceRecord.Status.LATE)
        self.assertEqual(services.summary(student=self.student)["percentage"], 75.0)

    def test_per_lecture_marks_are_separate_rows(self):
        d = datetime.date(2026, 1, 5)
        services.mark(student=self.student, date=d, period=1, status=AttendanceRecord.Status.PRESENT)
        services.mark(student=self.student, date=d, period=2, status=AttendanceRecord.Status.ABSENT)
        self.assertEqual(AttendanceRecord.objects.filter(student=self.student, date=d).count(), 2)
