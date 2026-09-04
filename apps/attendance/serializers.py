from rest_framework import serializers

from apps.attendance.models import AttendanceRecord, Student


class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ("id", "full_name", "roll_no", "class_section", "created_at")
        read_only_fields = ("created_at",)


class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = ("id", "student", "student_name", "date", "status", "marked_by", "created_at")
        read_only_fields = ("created_at",)


class MarkAttendanceSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    date = serializers.DateField()
    status = serializers.ChoiceField(choices=AttendanceRecord.Status.choices)


class AttendanceSummarySerializer(serializers.Serializer):
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    leave = serializers.IntegerField()
    total = serializers.IntegerField()
    percentage = serializers.FloatField()
