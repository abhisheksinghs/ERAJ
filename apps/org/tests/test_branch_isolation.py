"""
Branch isolation inside one client (ADR-001) and role enforcement (ADR-006),
through the real HTTP stack.

    python manage.py test apps.org.tests.test_branch_isolation
"""
from apps.core.testing import EraTestCase
from apps.library.models import Book
from apps.org.models import Role, RoleAssignment


class BranchIsolationTest(EraTestCase):
    def setUp(self):
        super().setUp()
        self.gaya = self.make_branch("gaya")
        self.patna_book = Book.objects.create(branch=self.branch, title="P", author="A", isbn="P-1")
        self.gaya_book = Book.objects.create(branch=self.gaya, title="G", author="A", isbn="G-1")
        self.librarian = self.make_user(Role.LIBRARIAN)

    def test_list_shows_only_own_branch(self):
        r = self.api(self.librarian).get("/api/library/books/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([b["isbn"] for b in r.json()["results"]], ["P-1"])

    def test_other_branch_detail_is_404(self):
        r = self.api(self.librarian).get(f"/api/library/books/{self.gaya_book.pk}/")
        self.assertEqual(r.status_code, 404)

    def test_choosing_a_branch_without_a_role_there_is_403(self):
        r = self.api(self.librarian, branch=self.gaya).get("/api/library/books/")
        self.assertEqual(r.status_code, 403)

    def test_all_branches_view_is_group_admin_only(self):
        self.assertEqual(self.api(self.librarian, branch="all").get("/api/library/books/").status_code, 403)
        group = self.make_user(Role.GROUP_ADMIN)
        r = self.api(group, branch="all").get("/api/library/books/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 2)

    def test_writes_need_a_single_branch(self):
        group = self.make_user(Role.GROUP_ADMIN)
        r = self.api(group, branch="all").post(
            "/api/library/books/", {"title": "x", "author": "y", "isbn": "z"}, content_type="application/json"
        )
        self.assertEqual(r.status_code, 403)

    def test_multi_branch_user_must_choose(self):
        RoleAssignment.objects.create(user=self.librarian, role=Role.LIBRARIAN, branch=self.gaya)
        self.assertEqual(self.api(self.librarian, branch=None).get("/api/library/books/").status_code, 400)
        self.assertEqual(self.api(self.librarian, branch=self.gaya).get("/api/library/books/").status_code, 200)

    def test_create_stamps_the_active_branch_not_the_payload(self):
        r = self.api(self.librarian).post(
            "/api/library/books/",
            {"title": "New", "author": "A", "isbn": "N-1", "branch": self.gaya.pk},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Book.objects.get(isbn="N-1").branch, self.branch)

    def test_foreign_keys_to_other_branch_are_rejected(self):
        gaya_student = self.make_student(branch=self.gaya)
        r = self.api(self.librarian).post(
            "/api/library/members/", {"student": gaya_student.pk}, content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)
        member = self.make_member()
        r = self.api(self.librarian).post(
            "/api/library/issues/", {"book": self.gaya_book.pk, "member": member.pk}, content_type="application/json"
        )
        self.assertEqual(r.status_code, 400)

    def test_role_without_permission_is_403(self):
        accountant = self.make_user(Role.ACCOUNTANT)
        self.assertEqual(self.api(accountant).get("/api/library/books/").status_code, 403)
        teacher = self.make_user(Role.TEACHER)
        api = self.api(teacher)
        self.assertEqual(api.get("/api/library/books/").status_code, 200)  # view allowed
        r = api.post("/api/library/books/", {"title": "x", "author": "y", "isbn": "t"}, content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_librarian_cannot_waive_fines(self):
        from apps.library.models import Fine, Issue

        member = self.make_member()
        issue = Issue.objects.create(branch=self.branch, book=self.patna_book, member=member, due_date="2026-01-01")
        fine = Fine.objects.create(branch=self.branch, member=member, issue=issue, amount="10.00")
        url = f"/api/library/fines/{fine.pk}/waive/"
        self.assertEqual(self.api(self.librarian).post(url).status_code, 403)
        self.assertEqual(self.api(self.make_user(Role.ADMIN)).post(url).status_code, 200)

    def test_user_with_no_roles_gets_nothing(self):
        nobody = self.make_user()
        self.assertEqual(self.api(nobody, branch=None).get("/api/library/books/").status_code, 400)


class UserManagementTest(EraTestCase):
    def test_branch_admin_cannot_edit_user_with_roles_elsewhere(self):
        gaya = self.make_branch("gaya")
        admin = self.make_user(Role.ADMIN)
        shared = self.make_user(Role.TEACHER)
        RoleAssignment.objects.create(user=shared, role=Role.TEACHER, branch=gaya)
        r = self.api(admin).patch(
            f"/api/org/users/{shared.pk}/", {"password": "takeover-pass-1"}, content_type="application/json"
        )
        self.assertEqual(r.status_code, 403)

    def test_branch_admin_cannot_grant_group_admin(self):
        admin = self.make_user(Role.ADMIN)
        r = self.api(admin).post(
            "/api/org/users/",
            {"email": "new@test.local", "roles": ["group_admin"]},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_admin_creates_staff_user_with_roles_in_own_branch(self):
        admin = self.make_user(Role.ADMIN)
        r = self.api(admin).post(
            "/api/org/users/",
            {"email": "lib@test.local", "first_name": "L", "roles": ["librarian"], "password": "a-long-password-1"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        ra = RoleAssignment.objects.get(user__email="lib@test.local")
        self.assertEqual((ra.role, ra.branch_id), (Role.LIBRARIAN, self.branch.pk))

    def test_me_lists_branches_roles_and_patterns(self):
        user = self.make_user(Role.LIBRARIAN)
        me = self.api(user, branch=None).get("/api/auth/me/").json()
        self.assertEqual(len(me["branches"]), 1)
        self.assertEqual(me["branches"][0]["roles"], ["librarian"])
        self.assertIn("library.*", me["branches"][0]["permissions"]["librarian"])
