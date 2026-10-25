from rest_framework import serializers

from apps.library.models import Book, Category, Fine, Hold, Issue, Member
from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField


class CategorySerializer(BranchScopedSerializer):
    class Meta:
        model = Category
        fields = ("id", "branch", "name")


class BookSerializer(BranchScopedSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)

    class Meta:
        model = Book
        fields = (
            "id", "branch", "title", "author", "isbn", "barcode", "publisher", "published_year",
            "category", "category_name", "tags", "shelf_location",
            "copies_total", "copies_available", "created_at",
        )
        read_only_fields = ("copies_available", "created_at")

    def validate_copies_total(self, value):
        if self.instance is None and value < 1:
            raise serializers.ValidationError("must be at least 1")
        return value

    def create(self, validated_data):
        validated_data["copies_available"] = validated_data.get("copies_total", 1)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "copies_total" in validated_data:
            delta = validated_data["copies_total"] - instance.copies_total
            instance.copies_available = max(0, instance.copies_available + delta)
        return super().update(instance, validated_data)


class MemberSerializer(BranchScopedSerializer):
    full_name = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    member_type = serializers.SerializerMethodField()
    open_loan_count = serializers.IntegerField(read_only=True)
    effective_borrow_limit = serializers.IntegerField(read_only=True)

    class Meta:
        model = Member
        fields = (
            "id", "branch", "student", "staff", "member_type", "full_name", "phone", "max_books",
            "open_loan_count", "effective_borrow_limit", "created_at",
        )
        read_only_fields = ("created_at",)

    def get_member_type(self, obj) -> str:
        return "student" if obj.student_id else "staff"

    def validate(self, attrs):
        student = attrs.get("student", getattr(self.instance, "student", None))
        staff = attrs.get("staff", getattr(self.instance, "staff", None))
        if bool(student) == bool(staff):
            raise serializers.ValidationError("Choose exactly one: a student or a staff member.")
        return attrs


class IssueSerializer(BranchScopedSerializer):
    book_title = serializers.CharField(source="book.title", read_only=True)
    member_name = serializers.CharField(source="member.full_name", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Issue
        fields = (
            "id", "branch", "book", "book_title", "member", "member_name",
            "due_date", "returned_at", "renewals", "is_overdue", "created_at",
        )
        read_only_fields = ("book", "member", "due_date", "returned_at", "renewals", "created_at")


class IssueCreateSerializer(serializers.Serializer):
    book = ScopedPrimaryKeyRelatedField(queryset=Book.objects.all())
    member = ScopedPrimaryKeyRelatedField(queryset=Member.objects.all())


class FineSerializer(BranchScopedSerializer):
    outstanding = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model = Fine
        fields = (
            "id", "branch", "member", "issue", "amount", "reason",
            "paid", "waived", "waived_by", "outstanding", "created_at",
        )
        read_only_fields = ("member", "issue", "amount", "reason", "waived", "waived_by", "created_at")


class HoldSerializer(BranchScopedSerializer):
    class Meta:
        model = Hold
        fields = ("id", "branch", "book", "member", "status", "created_at")
        read_only_fields = ("status", "created_at")


class IsbnLookupSerializer(serializers.Serializer):
    isbn = serializers.CharField(max_length=20)
    title = serializers.CharField()
    author = serializers.CharField()
    publisher = serializers.CharField(allow_blank=True)
    published_year = serializers.IntegerField(allow_null=True)
