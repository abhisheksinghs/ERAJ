from rest_framework import serializers

from apps.org.serializers import BranchScopedSerializer
from apps.people.models import Student
from apps.portal.models import ChangeRequest, StudentLeave


class OtpRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


class OtpVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "Enter the 6-digit code."})


class OutpassAskSerializer(serializers.Serializer):
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    return_by = serializers.TimeField(required=False)
    destination = serializers.CharField(max_length=200, required=False, allow_blank=True)
    reason = serializers.CharField(max_length=200)

    def validate(self, attrs):
        if attrs["to_date"] < attrs["from_date"]:
            raise serializers.ValidationError({"to_date": "Return date is before the leaving date."})
        return attrs


class LeaveAskSerializer(serializers.Serializer):
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    reason = serializers.CharField(max_length=300)


class ChangeAskSerializer(serializers.Serializer):
    field = serializers.ChoiceField(choices=ChangeRequest.Field.choices)
    new_value = serializers.CharField(max_length=500)


class DecideSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class StudentLeaveSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)
    days = serializers.SerializerMethodField()

    class Meta:
        model = StudentLeave
        fields = ("id", "branch", "student", "student_name", "admission_no", "from_date", "to_date", "days", "reason",
                  "requested_by", "status", "decided_by", "decided_at", "decision_note", "created_at")
        read_only_fields = fields

    def get_days(self, obj) -> int:
        return (obj.to_date - obj.from_date).days + 1


class ChangeRequestSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)
    guardian_name = serializers.CharField(source="guardian.full_name", read_only=True, default=None)
    field_name = serializers.CharField(source="get_field_display", read_only=True)

    class Meta:
        model = ChangeRequest
        fields = ("id", "branch", "student", "student_name", "admission_no", "guardian", "guardian_name", "field", "field_name",
                  "old_value", "new_value", "requested_by", "status", "decided_by", "decided_at", "decision_note", "created_at")
        read_only_fields = fields


class StudentLoginSerializer(BranchScopedSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True)

    class Meta:
        model = Student
        fields = ("id", "branch", "admission_no", "full_name", "email", "last_login")
        read_only_fields = fields


class StudentLoginCreateSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, max_length=128, write_only=True)
