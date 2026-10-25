from decimal import Decimal

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
    open_loan_count = serializers.SerializerMethodField()
    effective_borrow_limit = serializers.IntegerField(read_only=True)

    class Meta:
        model = Member
        fields = (
            "id", "branch", "student", "staff", "member_type", "full_name", "phone", "max_books",
            "open_loan_count", "effective_borrow_limit", "created_at",
        )
        read_only_fields = ("created_at",)

    def get_open_loan_count(self, obj) -> int:
        # Lists annotate `loans_open` (one query); a freshly created member falls back to the property.
        annotated = getattr(obj, "loans_open", None)
        return annotated if annotated is not None else obj.open_loan_count

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
    """`status`: open | paid | waived. A student's fine billed to Fees
    (`in_fees`) is paid at the fee counter; it cannot be marked paid here."""

    member_name = serializers.CharField(source="member.full_name", read_only=True)
    book_title = serializers.CharField(source="issue.book.title", read_only=True)
    in_fees = serializers.SerializerMethodField()
    outstanding = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    can_mark_paid = serializers.SerializerMethodField()

    class Meta:
        model = Fine
        fields = (
            "id", "branch", "member", "member_name", "issue", "book_title", "amount", "reason",
            "paid", "waived", "waived_by", "in_fees", "outstanding", "status", "can_mark_paid", "created_at",
        )
        read_only_fields = ("member", "issue", "amount", "reason", "waived", "waived_by", "created_at")

    def _fee_outstanding(self, obj):
        if hasattr(obj, "fee_outstanding"):
            return obj.fee_outstanding
        from apps.fees.models import Charge
        from apps.fees.selectors import charges_with_balance

        row = charges_with_balance(Charge.objects.filter(pk=obj.charge_id)).values("outstanding").first()
        return row["outstanding"] if row else None

    def get_in_fees(self, obj) -> bool:
        return obj.charge_id is not None

    def get_outstanding(self, obj) -> Decimal:
        if obj.waived:
            return Decimal("0.00")
        if obj.charge_id:
            owed = self._fee_outstanding(obj)
            return max(owed, Decimal("0.00")) if owed is not None else Decimal("0.00")
        return obj.outstanding

    def get_status(self, obj) -> str:
        if obj.waived:
            return "waived"
        return "paid" if (obj.paid if not obj.charge_id else self.get_outstanding(obj) == 0) else "open"

    def get_can_mark_paid(self, obj) -> bool:
        return not (obj.paid or obj.waived or obj.charge_id)

    def validate_paid(self, value):
        if self.instance is not None and self.instance.charge_id and value:
            raise serializers.ValidationError("This fine is on the student's fee account; collect it at the fee counter.")
        return value


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
