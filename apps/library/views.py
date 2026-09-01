from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny

from apps.library.models import Book


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ["id", "title", "author", "isbn", "copies_total", "copies_available"]


class BookListView(generics.ListCreateAPIView):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    # NOTE: AllowAny here for demo/test simplicity only. Production must use
    # JWTAuthentication (project default) + a permission class that also
    # checks the user belongs to this tenant, not just that they're logged in.
    permission_classes = [AllowAny]
