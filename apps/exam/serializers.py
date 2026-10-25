from rest_framework import serializers

from apps.exam.models import Exam, ExamSubject, GradeBand, GradeScale, Mark
from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.people.models import Section

MARKS = {"max_digits": 6, "decimal_places": 2}


class GradeBandSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeBand
        fields = ("grade", "min_percent", "grade_point", "is_fail", "remark")


class GradeScaleSerializer(BranchScopedSerializer):
    bands = GradeBandSerializer(many=True)

    class Meta:
        model = GradeScale
        fields = ("id", "branch", "name", "kind", "bands")

    def validate_bands(self, bands):
        if not bands:
            raise serializers.ValidationError("Add at least one grade band.")
        grades = [b["grade"] for b in bands]
        if len(set(grades)) != len(grades):
            raise serializers.ValidationError("Each grade can appear once.")
        if min(b["min_percent"] for b in bands) != 0:
            raise serializers.ValidationError("The lowest band must start at 0%.")
        return bands

    def _save_bands(self, scale, bands):
        scale.bands.all().delete()
        GradeBand.objects.bulk_create([GradeBand(scale=scale, **b) for b in bands])

    def create(self, validated_data):
        bands = validated_data.pop("bands")
        scale = super().create(validated_data)
        self._save_bands(scale, bands)
        return scale

    def update(self, instance, validated_data):
        bands = validated_data.pop("bands", None)
        scale = super().update(instance, validated_data)
        if bands is not None:
            self._save_bands(scale, bands)
        return scale


class ExamSubjectSerializer(BranchScopedSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    exam_name = serializers.CharField(source="exam.__str__", read_only=True)
    max_total = serializers.DecimalField(**MARKS, read_only=True)

    class Meta:
        model = ExamSubject
        fields = ("id", "branch", "exam", "exam_name", "subject", "subject_name", "max_theory", "max_practical", "max_total",
                  "pass_marks", "date", "start_time", "duration_minutes", "sequence")

    def validate(self, attrs):
        exam, subject = attrs.get("exam") or self.instance.exam, attrs.get("subject") or self.instance.subject
        if subject.program_id and subject.program_id != exam.program_id:
            raise serializers.ValidationError({"subject": "This subject belongs to another class or course."})
        mt = attrs.get("max_theory", getattr(self.instance, "max_theory", 0))
        mp = attrs.get("max_practical", getattr(self.instance, "max_practical", 0))
        if attrs.get("pass_marks", getattr(self.instance, "pass_marks", 0)) > mt + mp:
            raise serializers.ValidationError({"pass_marks": "Pass marks cannot exceed the maximum."})
        if mt + mp <= 0:
            raise serializers.ValidationError({"max_theory": "Maximum marks must be above 0."})
        return attrs


class ExamSerializer(BranchScopedSerializer):
    program_name = serializers.CharField(source="program.name", read_only=True)
    scale_name = serializers.CharField(source="scale.name", read_only=True)
    subject_count = serializers.IntegerField(read_only=True, default=None)
    is_published = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ("id", "branch", "name", "label", "name_hi", "academic_year", "program", "program_name", "term", "scale", "scale_name",
                  "weightage", "is_term_final", "sequence", "subject_count", "is_published", "published_at")
        read_only_fields = ("published_at",)

    def get_label(self, obj) -> str:
        return f"{obj.name} — {obj.program.name}" + (f" ({obj.term.name})" if obj.term_id else "")

    def get_is_published(self, obj) -> bool:
        return obj.published_at is not None


class MarkRowSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    theory = serializers.DecimalField(**MARKS, required=False, allow_null=True)
    practical = serializers.DecimalField(**MARKS, required=False, allow_null=True)
    status = serializers.ChoiceField(choices=Mark.Status.choices, default=Mark.Status.PRESENT)


class SaveMarksSerializer(serializers.Serializer):
    exam_subject = ScopedPrimaryKeyRelatedField(queryset=ExamSubject.objects.select_related("exam", "subject"))
    section = ScopedPrimaryKeyRelatedField(queryset=Section.objects.all())
    rows = MarkRowSerializer(many=True)


class LockSerializer(serializers.Serializer):
    exam = ScopedPrimaryKeyRelatedField(queryset=Exam.objects.all())
    section = ScopedPrimaryKeyRelatedField(queryset=Section.objects.all())
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
