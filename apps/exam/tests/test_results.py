"""python manage.py test apps.exam.tests.test_results"""
from decimal import Decimal

from django_tenants.test.cases import TenantTestCase

from apps.exam import services
from apps.exam.models import Student, Subject


class ResultsTest(TenantTestCase):
    def setUp(self):
        self.student = Student.objects.create(full_name="S1", roll_no="R1")
        self.maths = Subject.objects.create(name="Maths")
        self.science = Subject.objects.create(name="Science")

    def test_record_result_is_idempotent(self):
        services.record_result(student=self.student, subject=self.maths, exam_name="Midterm", marks_obtained=Decimal("40"))
        services.record_result(student=self.student, subject=self.maths, exam_name="Midterm", marks_obtained=Decimal("55"))
        self.assertEqual(self.student.results.count(), 1)
        self.assertEqual(self.student.results.first().marks_obtained, Decimal("55"))

    def test_student_report_overall_percentage(self):
        services.record_result(student=self.student, subject=self.maths, exam_name="Midterm", marks_obtained=Decimal("50"), max_marks=Decimal("100"))
        services.record_result(student=self.student, subject=self.science, exam_name="Midterm", marks_obtained=Decimal("30"), max_marks=Decimal("50"))
        report = services.student_report(student=self.student)
        # (50+30) / (100+50) = 53.3%
        self.assertAlmostEqual(report["overall_percentage"], 53.3, places=1)
