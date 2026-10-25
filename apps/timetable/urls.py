from rest_framework.routers import DefaultRouter

from apps.timetable import views

router = DefaultRouter()
router.register("schedules", views.BellScheduleViewSet, basename="bell-schedule")
router.register("rooms", views.RoomViewSet, basename="timetable-room")
router.register("loads", views.TeacherLoadViewSet, basename="teacher-load")
router.register("entries", views.TimetableEntryViewSet, basename="timetable-entry")
router.register("views", views.TimetableViewSet, basename="timetable-view")
router.register("absences", views.TeacherAbsenceViewSet, basename="teacher-absence")
router.register("substitutions", views.SubstitutionViewSet, basename="substitution")

urlpatterns = router.urls
