from rest_framework import serializers

from apps.exam.models import ExamResult, Student, Subject


class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ("id", "full_name", "roll_no", "class_section", "created_at")
        read_only_fields = ("created_at",)


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ("id", "name")


class ExamResultSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    percentage = serializers.FloatField(read_only=True)

    class Meta:
        model = ExamResult
        fields = (
            "id", "student", "student_name", "subject", "subject_name",
            "exam_name", "marks_obtained", "max_marks", "percentage", "created_at",
        )
        read_only_fields = ("created_at",)


class RecordResultSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    exam_name = serializers.CharField(max_length=100)
    marks_obtained = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    max_marks = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0, required=False, default=100)


class StudentReportSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    results = ExamResultSerializer(many=True)
    overall_percentage = serializers.FloatField()
