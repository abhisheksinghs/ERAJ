from decimal import Decimal

from rest_framework import serializers

from apps.exam.models import ExamResult
from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.people.models import Student, Subject


class ExamResultSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    percentage = serializers.FloatField(read_only=True)

    class Meta:
        model = ExamResult
        fields = (
            "id", "branch", "student", "student_name", "subject", "subject_name",
            "exam_name", "marks_obtained", "max_marks", "percentage", "created_at",
        )
        read_only_fields = ("created_at",)


class RecordResultSerializer(serializers.Serializer):
    student = ScopedPrimaryKeyRelatedField(queryset=Student.objects.all())
    subject = ScopedPrimaryKeyRelatedField(queryset=Subject.objects.all())
    exam_name = serializers.CharField(max_length=100)
    marks_obtained = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal("0"))
    max_marks = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal("0"), required=False, default=100)

    def validate(self, attrs):
        if attrs["marks_obtained"] > attrs.get("max_marks", 100):
            raise serializers.ValidationError({"marks_obtained": "cannot exceed max_marks"})
        return attrs


class StudentReportSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    results = ExamResultSerializer(many=True)
    overall_percentage = serializers.FloatField()
