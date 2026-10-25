from rest_framework.routers import DefaultRouter

from apps.people import views

router = DefaultRouter()
router.register("academic-years", views.AcademicYearViewSet, basename="academic-year")
router.register("departments", views.DepartmentViewSet, basename="department")
router.register("programs", views.ProgramViewSet, basename="program")
router.register("terms", views.TermViewSet, basename="term")
router.register("subjects", views.SubjectViewSet, basename="subject")
router.register("sections", views.SectionViewSet, basename="section")
router.register("staff", views.StaffViewSet, basename="staff")
router.register("students", views.StudentViewSet, basename="student")
router.register("guardians", views.GuardianViewSet, basename="guardian")
router.register("student-guardians", views.StudentGuardianViewSet, basename="student-guardian")
router.register("enrollments", views.EnrollmentViewSet, basename="enrollment")
router.register("teaching", views.TeachingAssignmentViewSet, basename="teaching")

urlpatterns = router.urls
