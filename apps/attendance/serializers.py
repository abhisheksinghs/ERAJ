from rest_framework import serializers

from apps.attendance.models import AttendanceCard, AttendanceDevice, AttendanceRecord, AttendanceSettings, Holiday, Punch
from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.people.models import Section, Staff, Student, Subject


class AttendanceSettingsSerializer(BranchScopedSerializer):
    class Meta:
        model = AttendanceSettings
        fields = ("id", "branch", "mode", "weekly_off", "threshold_percent", "long_absence_days", "auto_mark_from_punches")

    def validate_weekly_off(self, value):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if any(not p.isdigit() or int(p) > 6 for p in parts):
            raise serializers.ValidationError("Use weekday numbers 0 (Monday) to 6 (Sunday), comma separated.")
        return ",".join(parts)


class HolidaySerializer(BranchScopedSerializer):
    class Meta:
        model = Holiday
        fields = ("id", "branch", "date", "name", "name_hi")


class AttendanceRecordSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)
    section_name = serializers.CharField(source="section.__str__", read_only=True, default=None)

    class Meta:
        model = AttendanceRecord
        fields = (
            "id", "branch", "student", "student_name", "admission_no", "section", "section_name", "date", "period",
            "subject", "status", "source", "marked_by", "updated_at",
        )
        read_only_fields = fields


class MarkSectionSerializer(serializers.Serializer):
    section = ScopedPrimaryKeyRelatedField(queryset=Section.objects.all())
    date = serializers.DateField()
    period = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=20)
    subject = ScopedPrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    absent = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    statuses = serializers.DictField(child=serializers.ChoiceField(choices=AttendanceRecord.Status.choices),
                                     required=False, default=dict, help_text="{student_id: status} for anyone not present/absent")


class MarkResultSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    unchanged = serializers.IntegerField()


class SheetStudentSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    name = serializers.CharField()
    admission_no = serializers.CharField()
    roll_no = serializers.CharField()
    status = serializers.CharField(allow_null=True)
    source = serializers.CharField(allow_null=True)
    punched = serializers.BooleanField()


class SheetSerializer(serializers.Serializer):
    section = serializers.IntegerField()
    section_name = serializers.CharField()
    date = serializers.DateField()
    period = serializers.IntegerField(allow_null=True)
    holiday = serializers.CharField(allow_null=True)
    mode = serializers.CharField()
    students = SheetStudentSerializer(many=True)


class AttendanceDeviceSerializer(BranchScopedSerializer):
    push_url = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceDevice
        fields = ("id", "branch", "name", "brand", "model", "serial_no", "location", "allowed_ips", "is_active",
                  "last_seen_at", "token", "push_url")
        read_only_fields = ("last_seen_at", "token")

    def get_push_url(self, obj) -> str:
        request = self.context.get("request")
        host = request.get_host() if request else "<institution address>"
        if obj.brand in AttendanceDevice.ADMS_BRANDS:
            return f"Server address {host}, port 443 (ADMS / cloud server); serial {obj.serial_no}"
        if obj.brand == AttendanceDevice.Brand.GENERIC:
            return f"https://{host}/api/attendance/push/ with header X-Device-Key"
        return "Import the device's punch log from Excel/CSV"


class AttendanceCardSerializer(BranchScopedSerializer):
    person = serializers.SerializerMethodField()
    student = ScopedPrimaryKeyRelatedField(queryset=Student.objects.all(), required=False, allow_null=True)
    staff = ScopedPrimaryKeyRelatedField(queryset=Staff.objects.all(), required=False, allow_null=True)

    class Meta:
        model = AttendanceCard
        fields = ("id", "branch", "code", "student", "staff", "person", "is_active")

    def get_person(self, obj) -> str | None:
        p = obj.student or obj.staff
        return p.full_name if p else None

    def validate(self, attrs):
        student = attrs.get("student", getattr(self.instance, "student", None))
        staff = attrs.get("staff", getattr(self.instance, "staff", None))
        if bool(student) == bool(staff):
            raise serializers.ValidationError("Link the card to either a student or a staff member.")
        return attrs


class PunchSerializer(BranchScopedSerializer):
    person = serializers.SerializerMethodField()
    device_name = serializers.CharField(source="device.name", read_only=True, default=None)

    class Meta:
        model = Punch
        fields = ("id", "branch", "device", "device_name", "code", "punched_at", "student", "staff", "person", "source")
        read_only_fields = fields

    def get_person(self, obj) -> str | None:
        p = obj.student or obj.staff
        return p.full_name if p else None


class PunchImportSerializer(serializers.Serializer):
    file = serializers.FileField()
    device = ScopedPrimaryKeyRelatedField(queryset=AttendanceDevice.objects.all(), required=False, allow_null=True)
    dry_run = serializers.BooleanField(default=False)


class StudentPercentSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    name = serializers.CharField()
    admission_no = serializers.CharField()
    section = serializers.CharField()
    attended = serializers.FloatField()
    marked = serializers.IntegerField()
    percentage = serializers.FloatField()
