from rest_framework import serializers

from apps.library.models import Book, Category, Fine, Hold, Issue, Member


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name")


class BookSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)

    class Meta:
        model = Book
        fields = (
            "id", "title", "author", "isbn", "publisher", "published_year",
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


class MemberSerializer(serializers.ModelSerializer):
    open_loan_count = serializers.IntegerField(read_only=True)
    effective_borrow_limit = serializers.IntegerField(read_only=True)

    class Meta:
        model = Member
        fields = (
            "id", "full_name", "email", "phone", "max_books",
            "open_loan_count", "effective_borrow_limit", "created_at",
        )
        read_only_fields = ("created_at",)


class IssueSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source="book.title", read_only=True)
    member_name = serializers.CharField(source="member.full_name", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Issue
        fields = (
            "id", "book", "book_title", "member", "member_name",
            "due_date", "returned_at", "renewals", "is_overdue", "created_at",
        )
        read_only_fields = ("book", "member", "due_date", "returned_at", "renewals", "created_at")


class IssueCreateSerializer(serializers.Serializer):
    book = serializers.PrimaryKeyRelatedField(queryset=Book.objects.all())
    member = serializers.PrimaryKeyRelatedField(queryset=Member.objects.all())


class FineSerializer(serializers.ModelSerializer):
    outstanding = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model = Fine
        fields = (
            "id", "member", "issue", "amount", "reason",
            "paid", "waived", "waived_by", "outstanding", "created_at",
        )
        read_only_fields = ("member", "issue", "amount", "reason", "waived", "waived_by", "created_at")


class HoldSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hold
        fields = ("id", "book", "member", "status", "created_at")
        read_only_fields = ("status", "created_at")


class IsbnLookupSerializer(serializers.Serializer):
    isbn = serializers.CharField(max_length=20)
    title = serializers.CharField()
    author = serializers.CharField()
    publisher = serializers.CharField(allow_blank=True)
    published_year = serializers.IntegerField(allow_null=True)
