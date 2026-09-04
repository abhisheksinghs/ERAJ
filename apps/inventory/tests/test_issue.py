"""python manage.py test apps.inventory.tests.test_issue"""
from django_tenants.test.cases import TenantTestCase

from apps.core.exceptions import Conflict
from apps.inventory import services
from apps.inventory.models import Item


class IssueTest(TenantTestCase):
    def setUp(self):
        self.item = Item.objects.create(name="Laptop", sku="SKU-1", quantity_total=1, quantity_available=1)

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
