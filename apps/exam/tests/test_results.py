"""python manage.py test apps.exam.tests.test_results"""
from decimal import Decimal

from apps.exam import services
from apps.core.testing import EraTestCase
from apps.people.models import Subject


class ResultsTest(EraTestCase):
    def setUp(self):
        super().setUp()
        self.student = self.make_student()
        self.maths = Subject.objects.create(branch=self.branch, name="Maths", code="M")
        self.science = Subject.objects.create(branch=self.branch, name="Science", code="S")

    def test_record_result_is_idempotent(self):
        services.record_result(student=self.student, subject=self.maths, exam_name="Midterm", marks_obtained=Decimal("40"))
        services.record_result(student=self.student, subject=self.maths, exam_name="Midterm", marks_obtained=Decimal("55"))
        self.assertEqual(self.student.exam_results.count(), 1)
        self.assertEqual(self.student.exam_results.first().marks_obtained, Decimal("55"))

    def test_student_report_overall_percentage(self):
        services.record_result(student=self.student, subject=self.maths, exam_name="Midterm", marks_obtained=Decimal("50"), max_marks=Decimal("100"))
        services.record_result(student=self.student, subject=self.science, exam_name="Midterm", marks_obtained=Decimal("30"), max_marks=Decimal("50"))
        report = services.student_report(student=self.student)
        # (50+30) / (100+50) = 53.3%
        self.assertAlmostEqual(report["overall_percentage"], 53.3, places=1)
