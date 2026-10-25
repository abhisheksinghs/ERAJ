"""python manage.py test apps.inventory.tests.test_issue"""
from apps.core.exceptions import Conflict
from apps.core.testing import EraTestCase
from apps.inventory import services
from apps.inventory.models import Item


class IssueTest(EraTestCase):
    def setUp(self):
        super().setUp()
        self.item = Item.objects.create(branch=self.branch, name="Laptop", sku="SKU-1", quantity_total=1, quantity_available=1)

    def test_issue_decrements_and_blocks_at_zero(self):
        services.issue_item(item=self.item, issued_to="Front desk")
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity_available, 0)
        with self.assertRaises(Conflict):
            services.issue_item(item=self.item, issued_to="Someone else")

    def test_return_increments_and_is_not_repeatable(self):
        issue = services.issue_item(item=self.item, issued_to="Front desk")
        services.return_item(issue=issue)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity_available, 1)
        with self.assertRaises(Conflict):
            services.return_item(issue=issue)
