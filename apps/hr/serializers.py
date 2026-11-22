from rest_framework import serializers

from apps.hr.models import Designation, LeaveApplication, LeaveBalance, LeaveType, StaffAttendance, StaffDocument, StaffProfile
from apps.org.serializers import BranchScopedSerializer
from apps.people.models import Staff

MAX_DOC_BYTES = 5 * 1024 * 1024
DOC_TYPES = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
MAGIC = {".pdf": [b"%PDF"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"], ".png": [b"\x89PNG"]}


class DesignationSerializer(BranchScopedSerializer):
    class Meta:
        model = Designation
        fields = ("id", "branch", "name", "name_hi")


class StaffProfileSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)
    employee_code = serializers.CharField(source="staff.employee_code", read_only=True)
    bank_account_masked = serializers.CharField(read_only=True)

    class Meta:
        model = StaffProfile
        fields = (
            "id", "branch", "staff", "staff_name", "employee_code", "gender", "father_or_spouse", "address",
            "qualifications", "experience_years", "probation_end", "relieved_on", "exit_reason", "pan", "uan",
            "esic_ip", "pran", "bank_name", "bank_account", "bank_account_masked", "ifsc",
        )
        read_only_fields = ("relieved_on", "exit_reason")

    def to_internal_value(self, data):
        if hasattr(data, "copy"):
            data = data.copy()
            for f in ("pan", "ifsc"):
                if isinstance(data.get(f), str):
                    data[f] = data[f].strip().upper()
        return super().to_internal_value(data)

    def validate(self, attrs):
        staff = attrs.get("staff") or getattr(self.instance, "staff", None)
        if self.instance is not None and "staff" in attrs and attrs["staff"] != self.instance.staff:
            raise serializers.ValidationError({"staff": "A profile can't be moved to another staff member."})
        if self.instance is None and staff and StaffProfile.objects.filter(staff=staff).exists():
            raise serializers.ValidationError({"staff": "This staff member already has a profile; edit it instead."})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        view = self.context.get("view")
        if view is not None and getattr(view, "action", None) == "list":
            data["bank_account"] = instance.bank_account_masked  # full number only on the detail screen
        return data


class StaffDocumentSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)
    file = serializers.FileField(write_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = StaffDocument
        fields = ("id", "branch", "staff", "staff_name", "kind", "title", "file", "original_name", "content_type", "size",
                  "uploaded_by", "created_at", "download_url")
        read_only_fields = ("original_name", "content_type", "size", "uploaded_by", "created_at")

    def get_download_url(self, obj) -> str:
        return f"/api/hr/documents/{obj.pk}/download/"

    def validate_file(self, f):
        import os

        ext = os.path.splitext(f.name)[1].lower()
        if ext not in DOC_TYPES:
            raise serializers.ValidationError("Upload a PDF, JPG or PNG file.")
        if f.size > MAX_DOC_BYTES:
            raise serializers.ValidationError("The file is larger than 5 MB.")
        head = f.read(8)
        f.seek(0)
        if not any(head.startswith(m) for m in MAGIC[ext]):
            raise serializers.ValidationError("The file's contents don't match its type.")
        return f

    def create(self, validated_data):
        import os

        f = validated_data["file"]
        validated_data["original_name"] = os.path.basename(f.name)[:255]
        validated_data["content_type"] = DOC_TYPES[os.path.splitext(f.name)[1].lower()]
        validated_data["size"] = f.size
        return super().create(validated_data)


class StaffAttendanceSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)

    class Meta:
        model = StaffAttendance
        fields = ("id", "branch", "staff", "staff_name", "date", "status", "source", "unpaid", "leave", "marked_by")
        read_only_fields = fields


class MarkDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    absent = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    statuses = serializers.DictField(child=serializers.ChoiceField(choices=["present", "absent", "half_day", "on_duty"]),
                                     required=False, default=dict)


class LeaveTypeSerializer(BranchScopedSerializer):
    class Meta:
        model = LeaveType
        fields = ("id", "branch", "code", "name", "name_hi", "annual_days", "paid", "allow_half_day", "max_carry_forward")

    def validate_code(self, v):
        return v.strip().upper()


class LeaveBalanceSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)
    available = serializers.SerializerMethodField()

    class Meta:
        model = LeaveBalance
        fields = ("id", "branch", "staff", "staff_name", "leave_type", "leave_type_code", "year", "entitled", "used", "available")
        read_only_fields = ("staff", "leave_type", "year", "used")

    def get_available(self, obj) -> str:
        from apps.hr.services import available

        return str(available(balance=obj))


class LeaveApplicationSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)

    class Meta:
        model = LeaveApplication
        fields = ("id", "branch", "staff", "staff_name", "leave_type", "leave_type_code", "start", "end", "half_day", "days",
                  "reason", "status", "applied_by", "decided_by", "decided_at", "remarks", "created_at")
        read_only_fields = ("days", "status", "applied_by", "decided_by", "decided_at", "remarks", "created_at")


class SelfLeaveSerializer(serializers.Serializer):
    leave_type = serializers.IntegerField()
    start = serializers.DateField()
    end = serializers.DateField()
    half_day = serializers.BooleanField(default=False)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class LeaveDecisionSerializer(serializers.Serializer):
    remarks = serializers.CharField(required=False, allow_blank=True, default="")


class ExitSerializer(serializers.Serializer):
    relieved_on = serializers.DateField()
    reason = serializers.CharField()


class HRStaffSerializer(BranchScopedSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    relieved_on = serializers.DateField(source="hr_profile.relieved_on", read_only=True, default=None)
    exit_reason = serializers.CharField(source="hr_profile.exit_reason", read_only=True, default="")
    probation_end = serializers.DateField(source="hr_profile.probation_end", read_only=True, default=None)

    class Meta:
        model = Staff
        fields = ("id", "branch", "employee_code", "full_name", "designation", "department", "department_name", "phone",
                  "email", "date_joined", "employment_type", "status", "probation_end", "relieved_on", "exit_reason")
        read_only_fields = fields
