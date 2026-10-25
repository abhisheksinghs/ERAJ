"""Bulk student/staff import: all-or-nothing with row-level errors.

    python manage.py test apps.people.tests.test_import
"""
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.testing import EraTestCase
from apps.org.models import Role
from apps.people.models import Enrollment, Program, Staff, Student, StudentGuardian

HEADER = "admission_no,full_name,date_of_birth,gender,program_code,section,roll_no,guardian_name,guardian_phone,guardian_relation\n"


def csv_file(body: str, header: str = HEADER):
    return SimpleUploadedFile("students.csv", (header + body).encode("utf-8"), content_type="text/csv")


class StudentImportTest(EraTestCase):
    def setUp(self):
        super().setUp()
        Program.objects.create(branch=self.branch, code="C6", name="Class 6")
        self.api_ = self.api(self.make_user(Role.ADMIN))

    def test_valid_file_creates_students_enrollments_and_guardians(self):
        body = (
            "A1,Ravi Kumar,2014-05-01,male,C6,A,1,Mohan Kumar,9800000001,father\n"
            "A2,Priya Devi,01-06-2014,female,C6,A,2,Sita Devi,9800000002,mother\n"
        )
        r = self.api_.post("/api/people/students/import/", {"file": csv_file(body)})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["created"], 2)
        self.assertEqual(Student.objects.count(), 2)
        self.assertEqual(Enrollment.objects.filter(section__name="A").count(), 2)
        self.assertEqual(StudentGuardian.objects.filter(is_primary=True).count(), 2)

    def test_any_bad_row_saves_nothing_and_reports_row_numbers(self):
        body = (
            "A1,Ravi Kumar,2014-05-01,male,C6,A,1,,,\n"
            ",No Number,2014-05-01,male,C6,A,2,,,\n"
            "A3,Bad Date,31-31-2014,male,C9,A,3,,,\n"
        )
        r = self.api_.post("/api/people/students/import/", {"file": csv_file(body)})
        self.assertEqual(r.status_code, 400)
        rows = {e["row"]: e["errors"] for e in r.json()["errors"]}
        self.assertEqual(set(rows), {3, 4})
        self.assertTrue(any("admission_no is required" in e for e in rows[3]))
        self.assertTrue(any("C9" in e for e in rows[4]))
        self.assertEqual(Student.objects.count(), 0)

    def test_dry_run_validates_without_saving(self):
        r = self.api_.post(
            "/api/people/students/import/",
            {"file": csv_file("A1,Ravi,2014-05-01,male,C6,A,1,,,\n"), "dry_run": "true"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["dry_run"])
        self.assertEqual(Student.objects.count(), 0)

    def test_duplicate_admission_no_is_rejected(self):
        self.make_student(admission_no="A1")
        r = self.api_.post("/api/people/students/import/", {"file": csv_file("A1,Dup,,,,,,,,\n")})
        self.assertEqual(r.status_code, 400)


class StaffImportTest(EraTestCase):
    def test_staff_import_creates_departments(self):
        header = "employee_code,full_name,designation,department,date_joined\n"
        body = "E1,Asha Singh,Accountant,Accounts,2024-04-01\nE2,Raj Verma,Peon,Support,\n"
        r = self.api(self.make_user(Role.ADMIN)).post(
            "/api/people/staff/import/", {"file": csv_file(body, header)}
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Staff.objects.get(employee_code="E1").department.name, "Accounts")
