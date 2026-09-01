from django.urls import path

from apps.hostel import views

urlpatterns = [
    path("rooms/", views.RoomListView.as_view(), name="hostel-room-list"),
]
