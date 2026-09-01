from rest_framework import generics, serializers

from apps.accounts.permissions import RolePermission
from apps.library.models import Book


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ["id", "title", "author", "isbn", "copies_total", "copies_available"]


class BookListView(generics.ListCreateAPIView):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    permission_classes = [RolePermission]  # authenticated; read_only role -> GET only
