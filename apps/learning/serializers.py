from rest_framework import serializers

from apps.learning.models import (
    Attempt, DiaryEntry, Homework, Material, OnlineClass, OnlineTest, Question, Submission,
)
from apps.org.serializers import BranchScopedSerializer


class FileSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(source="original_name")
    size = serializers.IntegerField()


class HomeworkSerializer(BranchScopedSerializer):
    section_name = serializers.CharField(source="section.__str__", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True, default=None)
    files = FileSerializer(many=True, read_only=True)
    submitted = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Homework
        fields = ("id", "branch", "section", "section_name", "subject", "subject_name", "teacher", "teacher_name", "title",
                  "description", "due_date", "files", "submitted", "created_by", "created_at")
        read_only_fields = ("teacher", "created_by", "created_at")


class SubmissionSerializer(BranchScopedSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_no = serializers.CharField(source="student.admission_no", read_only=True)
    homework_title = serializers.CharField(source="homework.title", read_only=True)
    files = FileSerializer(many=True, read_only=True)

    class Meta:
        model = Submission
        fields = ("id", "branch", "homework", "homework_title", "student", "student_name", "admission_no", "text",
                  "submitted_at", "late", "grade", "remarks", "reviewed_by", "reviewed_at", "files")
        read_only_fields = fields


class GradeSerializer(serializers.Serializer):
    grade = serializers.CharField(required=False, allow_blank=True, default="", max_length=10)
    remarks = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class MaterialSerializer(BranchScopedSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    program_name = serializers.CharField(source="program.name", read_only=True, default=None)
    section_name = serializers.CharField(source="section.__str__", read_only=True, default=None)
    upload = serializers.FileField(write_only=True, required=False)
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields = ("id", "branch", "program", "program_name", "section", "section_name", "subject", "subject_name", "chapter",
                  "title", "description", "kind", "link", "upload", "has_file", "original_name", "teacher", "created_at")
        read_only_fields = ("teacher", "original_name", "created_at")

    def get_has_file(self, obj) -> bool:
        return bool(obj.file)

    def validate_upload(self, f):
        from apps.core.files import LEARNING, check_upload

        return check_upload(f, allowed=LEARNING, max_mb=10)

    def validate_link(self, v):
        if v and not v.startswith("https://"):
            raise serializers.ValidationError("Use an https:// link.")
        return v

    def validate(self, attrs):
        if not (attrs.get("program") or attrs.get("section") or self.instance):
            raise serializers.ValidationError({"program": "Choose a class or a section."})
        kind = attrs.get("kind", getattr(self.instance, "kind", "note"))
        if kind in ("video", "link") and not attrs.get("link", getattr(self.instance, "link", "")):
            raise serializers.ValidationError({"link": "Give the link."})
        return attrs


class OnlineClassSerializer(BranchScopedSerializer):
    section_name = serializers.CharField(source="section.__str__", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    joined = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = OnlineClass
        fields = ("id", "branch", "section", "section_name", "subject", "subject_name", "teacher", "title", "starts_at",
                  "ends_at", "link", "joined", "created_at")
        read_only_fields = ("teacher", "created_at")

    def validate_link(self, v):
        if not v.startswith("https://"):
            raise serializers.ValidationError("Use the https:// meeting link.")
        return v

    def validate(self, attrs):
        s = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        e = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if s and e and e <= s:
            raise serializers.ValidationError({"ends_at": "Ends before it starts."})
        return attrs


class QuestionSerializer(serializers.ModelSerializer):
    options = serializers.JSONField()

    class Meta:
        model = Question
        fields = ("id", "sequence", "text", "options", "correct", "marks")
        read_only_fields = ("id",)

    def validate_options(self, v):
        if isinstance(v, str):  # "Patna | Gaya | Bhagalpur" from a simple form
            v = [x.strip() for x in v.split("|")]
        if not isinstance(v, list) or not 2 <= len([x for x in v if str(x).strip()]) <= 6:
            raise serializers.ValidationError("2 to 6 choices (separate with |).")
        return [str(x).strip() for x in v if str(x).strip()]

    def validate(self, attrs):
        if attrs["correct"] >= len(attrs["options"]):
            raise serializers.ValidationError({"correct": "The right answer must be one of the choices (0 = first)."})
        return attrs


class OnlineTestSerializer(BranchScopedSerializer):
    section_name = serializers.CharField(source="section.__str__", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    questions = QuestionSerializer(many=True, required=False)
    question_count = serializers.SerializerMethodField()
    max_score = serializers.SerializerMethodField()

    class Meta:
        model = OnlineTest
        fields = ("id", "branch", "section", "section_name", "subject", "subject_name", "teacher", "title", "instructions",
                  "opens_at", "closes_at", "time_limit_minutes", "published", "show_answers", "questions",
                  "question_count", "max_score", "created_at")
        read_only_fields = ("teacher", "created_at")

    def get_question_count(self, obj) -> int:
        return len(obj.questions.all())

    def get_max_score(self, obj) -> str:
        return str(sum((q.marks for q in obj.questions.all()), 0))

    def validate(self, attrs):
        o = attrs.get("opens_at", getattr(self.instance, "opens_at", None))
        c = attrs.get("closes_at", getattr(self.instance, "closes_at", None))
        if o and c and c <= o:
            raise serializers.ValidationError({"closes_at": "Closes before it opens."})
        if self.instance is not None and "questions" in attrs and self.instance.attempts.exists():
            raise serializers.ValidationError({"questions": "Students have started this test; questions can't change."})
        seq = [q["sequence"] for q in attrs.get("questions", [])]
        if len(seq) != len(set(seq)):
            raise serializers.ValidationError({"questions": "Each question number once."})
        return attrs

    def _save_questions(self, test, questions):
        if questions is None:
            return
        test.questions.all().delete()
        Question.objects.bulk_create([Question(test=test, **{k: v for k, v in q.items() if k != "id"}) for q in questions])

    def create(self, validated_data):
        qs = validated_data.pop("questions", [])
        t = super().create(validated_data)
        self._save_questions(t, qs)
        return t

    def update(self, instance, validated_data):
        qs = validated_data.pop("questions", None)
        t = super().update(instance, validated_data)
        self._save_questions(t, qs)
        return t


class DiaryEntrySerializer(BranchScopedSerializer):
    section_name = serializers.CharField(source="section.__str__", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True, default=None)

    class Meta:
        model = DiaryEntry
        fields = ("id", "branch", "section", "section_name", "date", "period", "subject", "subject_name", "teacher",
                  "teacher_name", "topic", "notes")
        read_only_fields = ("teacher",)


class AttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attempt
        fields = ("id", "test", "started_at", "deadline", "submitted_at", "score", "max_score", "auto_submitted")
        read_only_fields = fields


