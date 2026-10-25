"""Permission map unit tests — pure Python, no database.

    python manage.py test apps.org.tests.test_rbac
"""
from django.test import SimpleTestCase

from apps.org.models import Role
from apps.org.permissions import required_perm
from apps.org.rbac import role_allows, roles_allow


class RbacMapTest(SimpleTestCase):
    def test_admin_runs_branch_but_cannot_create_branches(self):
        self.assertTrue(role_allows(Role.ADMIN, "fees.receipt.cancel"))
        self.assertFalse(role_allows(Role.ADMIN, "org.branch.manage"))
        self.assertTrue(role_allows(Role.GROUP_ADMIN, "org.branch.manage"))

    def test_accountant_cannot_cancel_receipts_or_approve_concessions(self):
        self.assertTrue(role_allows(Role.ACCOUNTANT, "fees.receipt.manage"))
        self.assertFalse(role_allows(Role.ACCOUNTANT, "fees.receipt.cancel"))
        self.assertFalse(role_allows(Role.ACCOUNTANT, "fees.concession.approve"))

    def test_librarian_scope(self):
        self.assertTrue(role_allows(Role.LIBRARIAN, "library.issue.return"))
        self.assertFalse(role_allows(Role.LIBRARIAN, "library.fine.waive"))
        self.assertFalse(role_allows(Role.LIBRARIAN, "fees.payment.view"))
        self.assertTrue(role_allows(Role.LIBRARIAN, "people.student.view"))
        self.assertFalse(role_allows(Role.LIBRARIAN, "people.student.manage"))
        self.assertFalse(role_allows(Role.LIBRARIAN, "org.branch.view"))  # no Settings menu

    def test_teacher_cannot_unlock_marks(self):
        self.assertTrue(role_allows(Role.TEACHER, "exam.marks.enter"))
        self.assertFalse(role_allows(Role.TEACHER, "exam.marks.unlock"))

    def test_portal_roles_reach_only_the_portal(self):
        for role in (Role.PARENT, Role.STUDENT):
            self.assertTrue(role_allows(role, "portal.child.view"))
            self.assertFalse(role_allows(role, "people.student.view"))

    def test_any_role_granting_is_enough(self):
        self.assertTrue(roles_allow({Role.LIBRARIAN, Role.ACCOUNTANT}, "fees.payment.view"))
        self.assertFalse(roles_allow(set(), "library.book.view"))


class RequiredPermTest(SimpleTestCase):
    class View:
        perm_resource = "library.issue"
        action_perms = {"renew": "library.issue.renew"}

    def _perm(self, action, method):
        v = self.View()
        v.action = action
        return required_perm(v, method)

    def test_mapping(self):
        self.assertEqual(self._perm("list", "GET"), "library.issue.view")
        self.assertEqual(self._perm("create", "POST"), "library.issue.manage")
        self.assertEqual(self._perm("renew", "POST"), "library.issue.renew")
        self.assertEqual(self._perm("report", "GET"), "library.issue.view")
        self.assertIsNone(self._perm("undeclared_write", "POST"))
