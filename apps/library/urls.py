from django.urls import path

from apps.library import views

urlpatterns = [
    path("books/", views.BookListView.as_view(), name="library-book-list"),
]
