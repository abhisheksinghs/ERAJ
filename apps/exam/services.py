"""Marks entry, locking and computed results (ADR-008).

Rules
  * absent  → shown "AB", counts 0, fails the subject
  * exempt  → left out of both marks and maximum (and of pass/fail)
  * not entered yet → counts 0 and the student is flagged `pending`
  * pass    → every subject's total ≥ its pass marks and the overall grade band is not a fail band
  * rank    → competition ranking on percentage (1, 2, 2, 4) within section and within class
  * annual  → per subject and overall: Σ(exam % × weightage) ÷ Σ weightage
  * SGPA    → Σ(credits × grade point) ÷ Σ credits for one exam; CGPA over all term-final exams
"""
from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.audit import record
from apps.core.exceptions import Conflict
from apps.exam.models import Exam, ExamLock, ExamSubject, GradeScale, Mark
from apps.people.models import Enrollment, Section, Student, TeachingAssignment

D0 = Decimal("0")
CENT = Decimal("0.01")


def q2(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ who / what
def students_of(exam: Exam, section: Section | None = None) -> list[tuple[Student, Section | None, str]]:
    """(student, section, roll) for the exam's class, active enrolments of its year (and term)."""
    qs = Enrollment.objects.filter(academic_year=exam.academic_year, program=exam.program, status=Enrollment.Status.ACTIVE)
    if exam.term_id:
        qs = qs.filter(term=exam.term)
    if section is not None:
        qs = qs.filter(section=section)
    rows = qs.select_related("student", "section").order_by("section__name", "roll_no", "student__full_name")
    return [(e.student, e.section, e.roll_no) for e in rows if e.student.deleted_at is None]


def may_enter(*, staff, exam_subject: ExamSubject, section: Section) -> bool:
    return staff is not None and TeachingAssignment.objects.filter(
        staff=staff, subject=exam_subject.subject, section=section
    ).exists()


def is_locked(exam: Exam, section: Section) -> bool:
    return ExamLock.objects.filter(exam=exam, section=section).exists()


# ------------------------------------------------------------------ marks entry
@transaction.atomic
def save_marks(*, exam_subject: ExamSubject, section: Section, rows: list[dict], by: str) -> int:
    exam = exam_subject.exam
    if section.program_id != exam.program_id:
        raise Conflict("This section is not in the exam's class.")
    if is_locked(exam, section):
        raise Conflict("Marks for this section are locked. Ask Admin to unlock them.")
    allowed = {s.pk for s, _, _ in students_of(exam, section)}
    changed = 0
    for row in rows:
        sid = row["student"]
        if sid not in allowed:
            raise Conflict(f"Student {sid} is not in {section}.")
        status = row.get("status") or Mark.Status.PRESENT
        theory, practical = row.get("theory"), row.get("practical")
        if status != Mark.Status.PRESENT:
            theory = practical = None
        else:
            if theory is not None and not (D0 <= theory <= exam_subject.max_theory):
                raise Conflict(f"Theory marks must be between 0 and {exam_subject.max_theory}.")
            if practical is not None and not (D0 <= practical <= exam_subject.max_practical):
                raise Conflict(f"Practical marks must be between 0 and {exam_subject.max_practical}.")
            if exam_subject.max_practical == 0:
                practical = None
        _, created = Mark.objects.update_or_create(
            exam_subject=exam_subject, student_id=sid,
            defaults={"branch": exam_subject.branch, "theory": theory, "practical": practical, "status": status, "entered_by": by},
        )
        changed += 1
    record("exam.marks_saved", actor=by, exam=exam.pk, subject=exam_subject.subject_id, section=section.pk, rows=changed)
    return changed


def grid(*, exam_subject: ExamSubject, section: Section) -> dict:
    exam = exam_subject.exam
    students = students_of(exam, section)
    marks = {m.student_id: m for m in Mark.objects.filter(exam_subject=exam_subject, student__in=[s for s, _, _ in students])}
    return {
        "exam": exam.pk, "exam_name": exam.name, "exam_subject": exam_subject.pk, "subject": exam_subject.subject.name,
        "section": section.pk, "section_name": str(section), "locked": is_locked(exam, section),
        "max_theory": exam_subject.max_theory, "max_practical": exam_subject.max_practical, "pass_marks": exam_subject.pass_marks,
        "rows": [
            {"student": s.pk, "name": s.full_name, "admission_no": s.admission_no, "roll_no": roll,
             "theory": marks[s.pk].theory if s.pk in marks else None,
             "practical": marks[s.pk].practical if s.pk in marks else None,
             "status": marks[s.pk].status if s.pk in marks else None}
            for s, _, roll in students
        ],
    }


@transaction.atomic
def lock(*, exam: Exam, section: Section, by: str) -> ExamLock:
    obj, created = ExamLock.objects.get_or_create(exam=exam, section=section, defaults={"branch": section.branch, "locked_by": by})
    if not created:
        raise Conflict("Already locked.")
    record("exam.locked", actor=by, exam=exam.pk, section=section.pk)
    return obj


@transaction.atomic
def unlock(*, exam: Exam, section: Section, by: str, reason: str) -> None:
    n, _ = ExamLock.objects.filter(exam=exam, section=section).delete()
    if not n:
        raise Conflict("Not locked.")
    record("exam.unlocked", actor=by, exam=exam.pk, section=section.pk, reason=reason)


# ------------------------------------------------------------------ results
def _competition_rank(items: list[tuple[int, Decimal]]) -> dict[int, int]:
    """[(student, pct)] → {student: rank}, ties share a rank and the next skips."""
    ranks, prev, rank = {}, None, 0
    for i, (sid, pct) in enumerate(sorted(items, key=lambda x: -x[1]), start=1):
        if pct != prev:
            rank, prev = i, pct
        ranks[sid] = rank
    return ranks


def _scale(exam: Exam) -> GradeScale:
    return GradeScale.objects.prefetch_related("bands").get(pk=exam.scale_id)


def exam_results(exam: Exam, section: Section | None = None) -> dict:
    """Results for every student of the exam's class (ranks always over the
    whole class; `section` only filters the rows returned)."""
    scale = _scale(exam)
    subjects = list(exam.subjects.select_related("subject").order_by("sequence", "subject__name"))
    everyone = students_of(exam)
    marks = defaultdict(dict)
    for m in Mark.objects.filter(exam_subject__exam=exam):
        marks[m.student_id][m.exam_subject_id] = m

    rows = []
    for student, sec, roll in everyone:
        lines, total, max_total, passed, pending, credits_x_gp, credits = [], D0, D0, True, False, D0, D0
        for es in subjects:
            m = marks[student.pk].get(es.pk)
            if m is None:
                pending = True
                status, obtained = None, D0
            else:
                status = m.status
                obtained = (m.theory or D0) + (m.practical or D0) if m.status == Mark.Status.PRESENT else D0
            if status == Mark.Status.EXEMPT:
                lines.append({"subject": es.subject_id, "name": es.subject.name, "status": "exempt", "display": "EX",
                              "theory": None, "practical": None, "total": None, "max": None, "grade": None, "passed": None})
                continue
            subject_pass = status == Mark.Status.PRESENT and obtained >= es.pass_marks
            pct = q2(obtained * 100 / es.max_total) if es.max_total else D0
            band = scale.band_for(pct)
            if band is not None and band.is_fail:
                subject_pass = False
            passed = passed and subject_pass
            total += obtained
            max_total += es.max_total
            if scale.kind == GradeScale.Kind.CREDIT:
                c = es.subject.credits or Decimal("1")
                credits += c
                credits_x_gp += c * (band.grade_point if band and subject_pass else D0)
            lines.append({
                "subject": es.subject_id, "name": es.subject.name, "status": status or "pending",
                "display": "AB" if status == Mark.Status.ABSENT else ("—" if status is None else format(q2(obtained).normalize(), "f")),
                "theory": m.theory if m and status == Mark.Status.PRESENT else None,
                "practical": m.practical if m and status == Mark.Status.PRESENT else None,
                "total": q2(obtained), "max": es.max_total, "grade": band.grade if band else None, "passed": subject_pass,
            })
        pct = q2(total * 100 / max_total) if max_total else D0
        band = scale.band_for(pct)
        if band is not None and band.is_fail:
            passed = False
        row = {
            "student": student.pk, "name": student.full_name, "admission_no": student.admission_no, "roll_no": roll,
            "section": sec.pk if sec else None, "section_name": str(sec) if sec else "",
            "subjects": lines, "total": q2(total), "max_total": max_total, "percentage": pct,
            "grade": band.grade if band else None, "passed": passed and not pending, "pending": pending,
            "failed_subjects": [ln["name"] for ln in lines if ln["passed"] is False],
        }
        if scale.kind == GradeScale.Kind.CREDIT:
            row["sgpa"] = q2(credits_x_gp / credits) if credits else D0
            row["credits"] = credits
        rows.append(row)

    class_rank = _competition_rank([(r["student"], r["percentage"]) for r in rows])
    by_section = defaultdict(list)
    for r in rows:
        by_section[r["section"]].append((r["student"], r["percentage"]))
    section_rank = {}
    for items in by_section.values():
        section_rank.update(_competition_rank(items))
    for r in rows:
        r["rank_class"], r["rank_section"] = class_rank[r["student"]], section_rank[r["student"]]
    if section is not None:
        rows = [r for r in rows if r["section"] == section.pk]
    return {"exam": exam.pk, "exam_name": exam.name, "program": str(exam.program), "scale_kind": scale.kind,
            "subjects": [{"subject": es.subject_id, "name": es.subject.name, "max": es.max_total, "pass_marks": es.pass_marks}
                         for es in subjects],
            "rows": sorted(rows, key=lambda r: (r["section_name"], r["rank_section"], r["name"]))}


def analysis(exam: Exam, section: Section | None = None) -> dict:
    res = exam_results(exam, section)
    subjects = []
    for s in res["subjects"]:
        vals = [ln for r in res["rows"] for ln in r["subjects"] if ln["subject"] == s["subject"] and ln["status"] in ("present", "absent")]
        totals = [ln["total"] for ln in vals]
        subjects.append({
            "subject": s["subject"], "name": s["name"], "appeared": len(vals),
            "highest": max(totals) if totals else None, "lowest": min(totals) if totals else None,
            "average": q2(sum(totals) / len(totals)) if totals else None,
            "pass_percent": q2(Decimal(sum(1 for ln in vals if ln["passed"])) * 100 / len(vals)) if vals else None,
        })
    rows = res["rows"]
    return {
        "exam": exam.pk, "students": len(rows), "passed": sum(1 for r in rows if r["passed"]),
        "pass_percent": q2(Decimal(sum(1 for r in rows if r["passed"])) * 100 / len(rows)) if rows else None,
        "subjects": subjects,
        "toppers": [{"student": r["student"], "name": r["name"], "section": r["section_name"], "percentage": r["percentage"],
                     "rank": r["rank_class"]} for r in sorted(rows, key=lambda r: r["rank_class"]) if r["rank_class"] <= 3],
        "failing": [{"student": r["student"], "name": r["name"], "section": r["section_name"], "subjects": r["failed_subjects"]}
                    for r in rows if r["failed_subjects"]],
    }


def annual_results(*, exams: list[Exam], section: Section | None = None) -> dict:
    """Combine exams of one class by weightage."""
    exams = [e for e in exams if e.weightage > 0]
    if not exams:
        raise Conflict("Choose exams with a weightage above 0.")
    if len({(e.program_id, e.academic_year_id) for e in exams}) != 1:
        raise Conflict("All exams must be of the same class and year.")
    per_exam = {e.pk: {r["student"]: r for r in exam_results(e, section)["rows"]} for e in exams}
    scale = _scale(exams[-1])
    students = per_exam[exams[0].pk].keys()
    subject_names = {}
    for e in exams:
        for es in e.subjects.select_related("subject"):
            subject_names[es.subject_id] = es.subject.name
    rows = []
    for sid in students:
        first = per_exam[exams[0].pk][sid]
        subj_rows = []
        for subj_id, name in subject_names.items():
            parts, wsum, acc = [], D0, D0
            for e in exams:
                ln = next((x for x in per_exam[e.pk].get(sid, {}).get("subjects", []) if x["subject"] == subj_id), None)
                if ln is None or ln["status"] == "exempt" or not ln["max"]:
                    continue
                pct = q2(ln["total"] * 100 / ln["max"])
                parts.append({"exam": e.pk, "exam_name": e.name, "display": ln["display"], "max": ln["max"], "percent": pct,
                              "weightage": e.weightage})
                acc += pct * e.weightage
                wsum += e.weightage
            weighted = q2(acc / wsum) if wsum else None
            band = scale.band_for(weighted) if weighted is not None else None
            subj_rows.append({"subject": subj_id, "name": name, "exams": parts, "weighted_percent": weighted,
                              "grade": band.grade if band else None})
        wsum = sum((e.weightage for e in exams), D0)
        overall = q2(sum((per_exam[e.pk][sid]["percentage"] * e.weightage for e in exams if sid in per_exam[e.pk]), D0) / wsum)
        band = scale.band_for(overall)
        rows.append({"student": sid, "name": first["name"], "admission_no": first["admission_no"], "roll_no": first["roll_no"],
                     "section": first["section"], "section_name": first["section_name"], "subjects": subj_rows,
                     "percentage": overall, "grade": band.grade if band else None,
                     "passed": all(per_exam[e.pk][sid]["passed"] for e in exams if sid in per_exam[e.pk]) and not (band and band.is_fail)})
    ranks = _competition_rank([(r["student"], r["percentage"]) for r in rows])
    for r in rows:
        r["rank_class"] = ranks[r["student"]]
    return {"exams": [{"exam": e.pk, "name": e.name, "weightage": e.weightage} for e in exams],
            "rows": sorted(rows, key=lambda r: (r["section_name"], r["rank_class"]))}


def cgpa(student: Student) -> dict:
    """CGPA over every term-final credit exam the student has sat."""
    exams = Exam.objects.filter(is_term_final=True, scale__kind=GradeScale.Kind.CREDIT,
                                subjects__marks__student=student).distinct().order_by("academic_year__start_date", "sequence")
    terms, cx, cr = [], D0, D0
    for e in exams:
        row = next((r for r in exam_results(e)["rows"] if r["student"] == student.pk), None)
        if row is None or not row.get("credits"):
            continue
        terms.append({"exam": e.pk, "name": e.name, "term": str(e.term) if e.term else "", "sgpa": row["sgpa"], "credits": row["credits"]})
        cx += row["sgpa"] * row["credits"]
        cr += row["credits"]
    return {"student": student.pk, "terms": terms, "cgpa": q2(cx / cr) if cr else None, "credits": cr}


@transaction.atomic
def publish(*, exam: Exam, by: str, publish: bool = True) -> Exam:
    exam.published_at = timezone.now() if publish else None
    exam.save(update_fields=["published_at", "updated_at"])
    record("exam.published" if publish else "exam.unpublished", actor=by, exam=exam.pk)
    return exam
