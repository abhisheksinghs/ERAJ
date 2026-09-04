from django.db import transaction

from apps.core.audit import record
from apps.exam.models import ExamResult


@transaction.atomic
def record_result(*, student, subject, exam_name, marks_obtained, max_marks=100):
    """Idempotent: re-recording the same (student, subject, exam) updates the
    marks instead of raising on the unique constraint."""
    result, _ = ExamResult.objects.update_or_create(
        student=student,
        subject=subject,
        exam_name=exam_name,
        defaults={"marks_obtained": marks_obtained, "max_marks": max_marks},
    )
    record(
        "exam.result_recorded",
        detail={"result": result.pk, "student": student.pk, "subject": subject.pk, "exam_name": exam_name},
    )
    return result


def student_report(*, student) -> dict:
    results = list(student.results.select_related("subject"))
    total_obtained = sum(float(r.marks_obtained) for r in results)
    total_max = sum(float(r.max_marks) for r in results)
    return {
        "student": student.pk,
        "results": results,
        "overall_percentage": round(total_obtained / total_max * 100, 1) if total_max else 0.0,
    }
