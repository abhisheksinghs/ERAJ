from django.db.models import Count, Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import IsOwner, RolePermission
from apps.core.exceptions import Conflict
from apps.library import services
from apps.library.filters import BookFilter, FineFilter, IssueFilter
from apps.library.isbn import lookup as isbn_lookup
from apps.library.models import Book, Category, Fine, Hold, Issue, Member
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


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [RolePermission]
    search_fields = ["name"]


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.select_related("category").all()
    serializer_class = BookSerializer
    permission_classes = [RolePermission]
    filterset_class = BookFilter
    search_fields = ["title", "author", "isbn"]
    ordering_fields = ["title", "created_at", "copies_available", "published_year"]

    @action(detail=False, methods=["get"])
    def lookup(self, request):
        isbn = request.query_params.get("isbn", "").strip()
        if not isbn:
            raise ValidationError({"isbn": "query parameter is required"})
        return Response(IsbnLookupSerializer(isbn_lookup(isbn)).data)


class MemberViewSet(viewsets.ModelViewSet):
    serializer_class = MemberSerializer
    permission_classes = [RolePermission]
    search_fields = ["full_name", "email"]
    ordering_fields = ["full_name", "created_at"]

    def get_queryset(self):
        return Member.objects.annotate(
            open_loan_count=Count("issues", filter=Q(issues__returned_at__isnull=True))
        )


class IssueViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Issue.objects.select_related("book", "member").all()
    permission_classes = [RolePermission]
    filterset_class = IssueFilter
    ordering_fields = ["due_date", "created_at"]

    def get_serializer_class(self):
        return IssueCreateSerializer if self.action == "create" else IssueSerializer

    def create(self, request, *args, **kwargs):
        data = IssueCreateSerializer(data=request.data)
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
    mixins.RetrieveModelMixin, mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    queryset = Fine.objects.select_related("member", "issue").all()
    serializer_class = FineSerializer
    permission_classes = [RolePermission]
    filterset_class = FineFilter
    ordering_fields = ["created_at", "amount"]

    @action(detail=True, methods=["post"], permission_classes=[IsOwner])
    def waive(self, request, pk=None):
        fine = services.waive_fine(fine=self.get_object(), by=request.user.email)
        return Response(FineSerializer(fine).data)


class HoldViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Hold.objects.select_related("book", "member").all()
    serializer_class = HoldSerializer
    permission_classes = [RolePermission]
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
        serializer.save()

    def perform_destroy(self, instance):
        instance.status = Hold.Status.CANCELLED
        instance.save(update_fields=["status", "updated_at"])
