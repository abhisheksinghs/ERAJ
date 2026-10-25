from rest_framework import serializers

from apps.org.serializers import BranchScopedSerializer
from apps.people.models import (
    AcademicYear,
    Department,
    Enrollment,
    Guardian,
    Program,
    Section,
    Staff,
    Student,
    StudentGuardian,
    Subject,
    Term,
    TeachingAssignment,
)


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = ("id", "name", "start_date", "end_date", "is_current")


class DepartmentSerializer(BranchScopedSerializer):
    class Meta:
        model = Department
        fields = ("id", "branch", "name")


class ProgramSerializer(BranchScopedSerializer):
    class Meta:
        model = Program
        fields = ("id", "branch", "name", "name_hi", "code", "kind", "sequence")


class TermSerializer(BranchScopedSerializer):
    class Meta:
        model = Term
        fields = ("id", "branch", "program", "name", "sequence")


class SubjectSerializer(BranchScopedSerializer):
    class Meta:
        model = Subject
        fields = ("id", "branch", "name", "name_hi", "code", "program", "term", "credits", "has_practical")


class SectionSerializer(BranchScopedSerializer):
    program_name = serializers.CharField(source="program.name", read_only=True)
    class_teacher_name = serializers.CharField(source="class_teacher.full_name", read_only=True, default=None)
    student_count = serializers.IntegerField(read_only=True)
    label = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = (
            "id", "branch", "academic_year", "program", "program_name", "term", "name", "label",
            "class_teacher", "class_teacher_name", "capacity", "student_count",
        )

    def get_label(self, obj) -> str:
        return f"{obj.program.name}-{obj.name}" + (f" ({obj.term.name})" if obj.term_id else "")


class StaffSerializer(BranchScopedSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)

    class Meta:
        model = Staff
        fields = (
            "id", "branch", "employee_code", "full_name", "name_hi", "designation", "department",
            "department_name", "phone", "email", "date_of_birth", "date_joined", "employment_type",
            "status", "created_at",
        )
        read_only_fields = ("created_at",)


class EnrollmentSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)
    program_name = serializers.CharField(source="program.name", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True, default=None)

    class Meta:
        model = Enrollment
        fields = (
            "id", "branch", "student", "student_name", "admission_no", "academic_year", "program",
            "program_name", "term", "section", "section_name", "roll_no", "status",
        )

    def validate(self, attrs):
        section = attrs.get("section") or getattr(self.instance, "section", None)
        program = attrs.get("program") or getattr(self.instance, "program", None)
        year = attrs.get("academic_year") or getattr(self.instance, "academic_year", None)
        if section and (section.program_id != program.pk or section.academic_year_id != year.pk):
            raise serializers.ValidationError({"section": "Section belongs to a different program or year."})
        term = attrs.get("term") or getattr(self.instance, "term", None)
        if term and term.program_id != program.pk:
            raise serializers.ValidationError({"term": "Term belongs to a different program."})
        return attrs


class GuardianSerializer(BranchScopedSerializer):
    class Meta:
        model = Guardian
        fields = ("id", "branch", "full_name", "phone", "alt_phone", "email", "occupation", "address")


class StudentGuardianSerializer(BranchScopedSerializer):
    guardian_name = serializers.CharField(source="guardian.full_name", read_only=True)
    guardian_phone = serializers.CharField(source="guardian.phone", read_only=True)

    class Meta:
        model = StudentGuardian
        fields = ("id", "branch", "student", "guardian", "guardian_name", "guardian_phone", "relation", "is_primary")


class StudentSerializer(BranchScopedSerializer):
    current_program = serializers.SerializerMethodField()
    current_section = serializers.SerializerMethodField()
    primary_guardian = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = (
            "id", "branch", "admission_no", "full_name", "name_hi", "date_of_birth", "gender",
            "phone", "email", "address", "photo", "admission_date", "status",
            "current_program", "current_section", "primary_guardian", "created_at",
        )
        read_only_fields = ("created_at",)

    def _enrollment(self, obj):
        if not hasattr(obj, "_enrollment_cache"):
            obj._enrollment_cache = obj.current_enrollment
        return obj._enrollment_cache

    def get_current_program(self, obj) -> str | None:
        e = self._enrollment(obj)
        return e.program.name if e else None

    def get_current_section(self, obj) -> str | None:
        e = self._enrollment(obj)
        return e.section.name if e and e.section else None

    def get_primary_guardian(self, obj) -> dict | None:
        link = next((g for g in obj.guardian_links.all() if g.is_primary), None)
        if not link:
            return None
        return {"id": link.guardian_id, "name": link.guardian.full_name, "phone": link.guardian.phone}


class ImportResultSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.DictField())
    dry_run = serializers.BooleanField()


class TeachingAssignmentSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    section_name = serializers.CharField(source="section.__str__", read_only=True)
    label = serializers.SerializerMethodField()

    class Meta:
        model = TeachingAssignment
        fields = ("id", "branch", "staff", "staff_name", "subject", "subject_name", "section", "section_name",
                  "periods_per_week", "label")

    def get_label(self, obj) -> str:
        return f"{obj.section} · {obj.subject.name} · {obj.staff.full_name}"

    def validate(self, attrs):
        subject, section = attrs.get("subject"), attrs.get("section")
        if subject and section and subject.program_id and subject.program_id != section.program_id:
            raise serializers.ValidationError({"subject": "This subject belongs to another class or course."})
        return attrs
