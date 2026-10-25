from django.db.models import Count, Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.exceptions import Conflict
from apps.library import services
from apps.library.filters import BookFilter, FineFilter, IssueFilter
from apps.library.isbn import lookup as isbn_lookup
from apps.library.models import Book, Category, Fine, Hold, Issue, Member
from apps.org.mixins import BranchScopedViewSetMixin
from apps.library.serializers import (
    BookSerializer,
    CategorySerializer,
    FineSerializer,
    HoldSerializer,
    IsbnLookupSerializer,
    IssueCreateSerializer,
    IssueSerializer,
    MemberSerializer,
)


class CategoryViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    perm_resource = "library.category"
    search_fields = ["name"]


class BookViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Book.objects.select_related("category").all()
    serializer_class = BookSerializer
    perm_resource = "library.book"
    filterset_class = BookFilter
    search_fields = ["title", "author", "isbn", "barcode"]
    ordering_fields = ["title", "created_at", "copies_available", "published_year"]

    @action(detail=False, methods=["get"])
    def lookup(self, request):
        isbn = request.query_params.get("isbn", "").strip()
        if not isbn:
            raise ValidationError({"isbn": "query parameter is required"})
        return Response(IsbnLookupSerializer(isbn_lookup(isbn)).data)


class MemberViewSet(BranchScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = MemberSerializer
    perm_resource = "library.member"
    search_fields = ["student__full_name", "student__admission_no", "staff__full_name", "staff__employee_code"]
    ordering_fields = ["created_at"]
    filterset_fields = ["student", "staff"]
    queryset = Member.objects.select_related("student", "staff").annotate(
        open_loan_count=Count("issues", filter=Q(issues__returned_at__isnull=True))
    )


class IssueViewSet(
    BranchScopedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Issue.objects.select_related("book", "member__student", "member__staff").all()
    perm_resource = "library.issue"
    action_perms = {"return_book": "library.issue.return", "renew": "library.issue.renew"}
    filterset_class = IssueFilter
    ordering_fields = ["due_date", "created_at"]

    def get_serializer_class(self):
        return IssueCreateSerializer if self.action == "create" else IssueSerializer

    def create(self, request, *args, **kwargs):
        data = IssueCreateSerializer(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)
        issue = services.issue_book(**data.validated_data)
        return Response(IssueSerializer(issue).data, status=201)

    @action(detail=True, methods=["post"], url_path="return")
    def return_book(self, request, pk=None):
        issue, fine = services.return_book(issue=self.get_object())
        return Response(
            {"issue": IssueSerializer(issue).data, "fine": FineSerializer(fine).data if fine else None}
        )

    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        return Response(IssueSerializer(services.renew_issue(issue=self.get_object())).data)


class FineViewSet(
    BranchScopedViewSetMixin,
    mixins.RetrieveModelMixin, mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    queryset = Fine.objects.select_related("member", "issue").all()
    serializer_class = FineSerializer
    perm_resource = "library.fine"
    action_perms = {"waive": "library.fine.waive"}
    filterset_class = FineFilter
    ordering_fields = ["created_at", "amount"]

    @action(detail=True, methods=["post"])
    def waive(self, request, pk=None):
        fine = services.waive_fine(fine=self.get_object(), by=request.user.email)
        return Response(FineSerializer(fine).data)


class HoldViewSet(
    BranchScopedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Hold.objects.select_related("book", "member").all()
    serializer_class = HoldSerializer
    perm_resource = "library.hold"
    filterset_fields = ["book", "member", "status"]

    def perform_create(self, serializer):
        book = serializer.validated_data["book"]
        member = serializer.validated_data["member"]
        if book.copies_available > 0:
            raise Conflict("Copies are available — issue the book instead of holding it.")
        if Hold.objects.filter(
            book=book, member=member, status__in=[Hold.Status.WAITING, Hold.Status.READY]
        ).exists():
            raise Conflict("Member already has an active hold on this title.")
        super().perform_create(serializer)

    def perform_destroy(self, instance):
        instance.status = Hold.Status.CANCELLED
        instance.save(update_fields=["status", "updated_at"])
