from rest_framework import serializers

from apps.attendance.models import AttendanceRecord
from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.people.models import Student, Subject


class AttendanceRecordSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = (
            "id", "branch", "student", "student_name", "admission_no", "date", "period", "subject",
            "status", "marked_by", "created_at",
        )
        read_only_fields = ("marked_by", "created_at")


class MarkAttendanceSerializer(serializers.Serializer):
    student = ScopedPrimaryKeyRelatedField(queryset=Student.objects.all())
    date = serializers.DateField()
    status = serializers.ChoiceField(choices=AttendanceRecord.Status.choices)
    period = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    subject = ScopedPrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)


class AttendanceSummarySerializer(serializers.Serializer):
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    leave = serializers.IntegerField()
    late = serializers.IntegerField()
    half_day = serializers.IntegerField()
    total = serializers.IntegerField()
    percentage = serializers.FloatField()
