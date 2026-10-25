"""Exam acceptance scenarios (scope doc, Exam). Real tenant schema.

    python manage.py test apps.exam.tests.test_results
"""
from decimal import Decimal

from django_tenants.utils import schema_context

from apps.core.exceptions import Conflict
from apps.core.models import AuditLog
from apps.core.testing import EraTestCase
from apps.exam import services
from apps.exam.models import Exam, ExamSubject, GradeBand, GradeScale, Mark
from apps.people.models import Enrollment, Program, Section, Subject, TeachingAssignment, Term

D = Decimal
CBSE = [("A1", 91), ("A2", 81), ("B1", 71), ("B2", 61), ("C1", 51), ("C2", 41), ("D", 33), ("E", 0)]


class ExamBase(EraTestCase):
    def setUp(self):
        super().setUp()
        self.program = Program.objects.create(branch=self.branch, code="C9", name="Class 9")
        self.scale = GradeScale.objects.create(branch=self.branch, name="CBSE 8-point")
        for grade, low in CBSE:
            GradeBand.objects.create(scale=self.scale, grade=grade, min_percent=low, is_fail=grade == "E")
        self.class_teacher = self.make_staff()
        self.section = Section.objects.create(branch=self.branch, academic_year=self.year, program=self.program, name="A",
                                              class_teacher=self.class_teacher)
        self.subjects = [Subject.objects.create(branch=self.branch, code=f"S{i}", name=n, program=self.program)
                         for i, n in enumerate(["Hindi", "English", "Maths", "Science", "Social Science", "Sanskrit"], 1)]
        self.students = []
        for roll in range(1, 6):
            s = self.make_student()
            Enrollment.objects.create(branch=self.branch, student=s, academic_year=self.year, program=self.program,
                                      section=self.section, roll_no=str(roll))
            self.students.append(s)

    def exam(self, name="Half-Yearly", weightage=0, max_marks=100, scale=None, **kw):
        exam = Exam.objects.create(branch=self.branch, name=name, academic_year=self.year, program=self.program,
                                   scale=scale or self.scale, weightage=weightage, **kw)
        for i, subj in enumerate(self.subjects, 1):
            ExamSubject.objects.create(branch=self.branch, exam=exam, subject=subj, max_theory=max_marks,
                                       pass_marks=D(max_marks) * D("0.33"), sequence=i)
        return exam

    def put(self, exam, subject, marks: dict, status=None):
        es = exam.subjects.get(subject=subject)
        services.save_marks(exam_subject=es, section=self.section, by="t",
                            rows=[{"student": s.pk, "theory": D(v) if v is not None else None,
                                   "status": (status or {}).get(s, "present")} for s, v in marks.items()])


class MarksEntryTest(ExamBase):
    def test_subject_teacher_enters_only_own_subject(self):
        exam = self.exam()
        self.assertEqual(exam.subjects.count(), 6)
        maths_staff = self.make_staff()
        maths_teacher = self.make_user("teacher")
        maths_staff.user = maths_teacher
        maths_staff.save()
        TeachingAssignment.objects.create(branch=self.branch, staff=maths_staff, subject=self.subjects[2], section=self.section)
        api = self.api(maths_teacher)
        maths = exam.subjects.get(subject=self.subjects[2])
        hindi = exam.subjects.get(subject=self.subjects[0])
        row = [{"student": self.students[0].pk, "theory": "78"}]
        r = api.post("/api/exam/marks/save/", {"exam_subject": maths.pk, "section": self.section.pk, "rows": row}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        r = api.post("/api/exam/marks/save/", {"exam_subject": hindi.pk, "section": self.section.pk, "rows": row}, content_type="application/json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(api.get(f"/api/exam/marks/grid/?exam_subject={hindi.pk}&section={self.section.pk}").status_code, 403)
        # Admin enters any subject; marks above the maximum are refused
        admin = self.api(self.make_user("admin"))
        r = admin.post("/api/exam/marks/save/", {"exam_subject": hindi.pk, "section": self.section.pk,
                                                 "rows": [{"student": self.students[0].pk, "theory": "101"}]}, content_type="application/json")
        self.assertEqual(r.status_code, 409)

    def test_absentee_is_ab_not_zero_and_ranks_skip(self):
        exam = self.exam()
        a, b, c, d, e = self.students
        for subj in self.subjects:
            self.put(exam, subj, {a: 90, b: 80, c: 80, d: 70, e: None}, status={e: "absent"} if subj == self.subjects[2] else {})
        for subj in self.subjects:
            if subj != self.subjects[2]:
                self.put(exam, subj, {e: 95})
        rows = {r["student"]: r for r in services.exam_results(exam)["rows"]}
        maths_e = next(x for x in rows[e.pk]["subjects"] if x["name"] == "Maths")
        self.assertEqual((maths_e["display"], maths_e["passed"]), ("AB", False))
        self.assertFalse(rows[e.pk]["passed"])
        self.assertEqual(rows[e.pk]["failed_subjects"], ["Maths"])
        self.assertEqual(rows[e.pk]["total"], D("475.00"))  # 5 × 95, AB counts 0
        self.assertEqual([rows[s.pk]["rank_class"] for s in (a, b, c, d, e)], [1, 2, 2, 5, 4])  # 79.17% for e
        self.assertEqual((rows[a.pk]["grade"], rows[b.pk]["grade"], rows[d.pk]["grade"]), ("A2", "B1", "B2"))

    def test_lock_refuses_teacher_edit_and_admin_unlock_is_audited(self):
        exam = self.exam()
        teacher = self.make_user("teacher")
        self.class_teacher.user = teacher
        self.class_teacher.save()
        TeachingAssignment.objects.create(branch=self.branch, staff=self.class_teacher, subject=self.subjects[0], section=self.section)
        api = self.api(teacher)
        body = {"exam": exam.pk, "section": self.section.pk}
        self.assertEqual(api.post("/api/exam/marks/lock/", body, content_type="application/json").status_code, 200)
        es = exam.subjects.get(subject=self.subjects[0])
        r = api.post("/api/exam/marks/save/", {"exam_subject": es.pk, "section": self.section.pk,
                                               "rows": [{"student": self.students[0].pk, "theory": "50"}]}, content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(api.post("/api/exam/marks/unlock/", {**body, "reason": "x"}, content_type="application/json").status_code, 403)
        admin = self.api(self.make_user("admin"))
        self.assertEqual(admin.post("/api/exam/marks/unlock/", body, content_type="application/json").status_code, 400)  # reason needed
        r = admin.post("/api/exam/marks/unlock/", {**body, "reason": "Re-evaluation of Hindi"}, content_type="application/json")
        self.assertEqual(r.status_code, 200)
        with schema_context("public"):
            log = AuditLog.objects.filter(action="exam.unlocked").latest("id")
        self.assertEqual(log.detail["reason"], "Re-evaluation of Hindi")
        r = api.post("/api/exam/marks/save/", {"exam_subject": es.pk, "section": self.section.pk,
                                               "rows": [{"student": self.students[0].pk, "theory": "50"}]}, content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_only_class_teacher_locks(self):
        exam = self.exam()
        other = self.make_staff()
        user = self.make_user("teacher")
        other.user = user
        other.save()
        r = self.api(user).post("/api/exam/marks/lock/", {"exam": exam.pk, "section": self.section.pk}, content_type="application/json")
        self.assertEqual(r.status_code, 403)


class ResultsTest(ExamBase):
    def test_class_report_cards_one_pdf_with_band_grades(self):
        exam = self.exam()
        for i, subj in enumerate(self.subjects):
            self.put(exam, subj, {s: 95 - 10 * n for n, s in enumerate(self.students)})
        res = services.exam_results(exam, self.section)
        self.assertEqual([r["grade"] for r in res["rows"]], ["A1", "A2", "B1", "B2", "C1"])
        from apps.exam.pdf import report_cards_document

        doc = report_cards_document(exam=exam, result=res, rows=res["rows"])
        self.assertEqual(len(doc.pages), 5)
        r = self.api(self.make_user("admin")).get(f"/api/exam/results/report-cards/?exam={exam.pk}&section={self.section.pk}")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
        a = services.analysis(exam)
        maths = next(s for s in a["subjects"] if s["name"] == "Maths")
        self.assertEqual((maths["highest"], maths["lowest"], maths["average"], maths["pass_percent"]), (D("95.00"), D("55.00"), D("75.00"), D("100.00")))
        self.assertEqual([t["rank"] for t in a["toppers"]], [1, 2, 3])

    def test_annual_card_combines_30_and_70_weightage(self):
        half = self.exam("Half-Yearly", weightage=30, max_marks=50, sequence=1)
        annual = self.exam("Annual", weightage=70, max_marks=100, sequence=2)
        s = self.students[0]
        for subj in self.subjects:
            self.put(half, subj, {s: 40})    # 80 %
            self.put(annual, subj, {s: 90})  # 90 %
        res = services.annual_results(exams=[half, annual])
        row = next(r for r in res["rows"] if r["student"] == s.pk)
        self.assertEqual(row["percentage"], D("87.00"))  # 0.3 × 80 + 0.7 × 90
        self.assertEqual(row["subjects"][0]["weighted_percent"], D("87.00"))
        self.assertEqual(row["grade"], "A2")
        r = self.api(self.make_user("admin")).get(f"/api/exam/results/annual-cards/?exams={half.pk},{annual.pk}&student={s.pk}")
        self.assertEqual(r["Content-Type"], "application/pdf")
        with self.assertRaises(Conflict):
            services.annual_results(exams=[self.exam("Unit test 1", weightage=0)])

    def test_sgpa_and_cgpa_match_a_manual_calculation(self):
        course = Program.objects.create(branch=self.branch, code="BSC", name="B.Sc.", kind="course")
        sem1 = Term.objects.create(branch=self.branch, program=course, name="Semester 1", sequence=1)
        sem2 = Term.objects.create(branch=self.branch, program=course, name="Semester 2", sequence=2)
        scale = GradeScale.objects.create(branch=self.branch, name="UGC 10-point", kind="credit")
        for grade, low, gp, fail in [("O", 90, 10, False), ("A+", 80, 9, False), ("A", 70, 8, False), ("B+", 60, 7, False),
                                     ("B", 50, 6, False), ("C", 40, 5, False), ("F", 0, 0, True)]:
            GradeBand.objects.create(scale=scale, grade=grade, min_percent=low, grade_point=gp, is_fail=fail)
        student = self.make_student()
        exams = []
        for term, subjects in [(sem1, [("Physics", 4, 92), ("Maths", 4, 75), ("English", 2, 63)]),
                               (sem2, [("Chemistry", 4, 81), ("Lab", 2, 55)])]:
            sec = Section.objects.create(branch=self.branch, academic_year=self.year, program=course, term=term, name="A")
            Enrollment.objects.create(branch=self.branch, student=student, academic_year=self.year, program=course, term=term, section=sec)
            exam = Exam.objects.create(branch=self.branch, name=f"End-sem {term.sequence}", academic_year=self.year, program=course,
                                       term=term, scale=scale, is_term_final=True)
            for name, credits, got in subjects:
                subj = Subject.objects.create(branch=self.branch, code=name[:4], name=name, program=course, term=term, credits=credits)
                es = ExamSubject.objects.create(branch=self.branch, exam=exam, subject=subj, max_theory=100, pass_marks=40)
                Mark.objects.create(branch=self.branch, exam_subject=es, student=student, theory=got)
            exams.append(exam)
        sem1_row = services.exam_results(exams[0])["rows"][0]
        self.assertEqual(sem1_row["sgpa"], D("8.60"))   # (4×10 + 4×8 + 2×7) / 10
        sem2_row = services.exam_results(exams[1])["rows"][0]
        self.assertEqual(sem2_row["sgpa"], D("8.00"))   # (4×9 + 2×6) / 6
        self.assertEqual(services.cgpa(student)["cgpa"], D("8.38"))  # (86 + 48) / 16 = 8.375
