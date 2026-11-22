from rest_framework.routers import DefaultRouter

from apps.inventory import views

router = DefaultRouter()
router.register("stores", views.StoreViewSet, basename="inventory-store")
router.register("vendors", views.VendorViewSet, basename="inventory-vendor")
router.register("items", views.ItemViewSet, basename="inventory-item")
router.register("moves", views.StockMoveViewSet, basename="inventory-move")
router.register("issues", views.IssueRecordViewSet, basename="inventory-issue")
router.register("requisitions", views.RequisitionViewSet, basename="inventory-requisition")
router.register("orders", views.PurchaseOrderViewSet, basename="inventory-order")
router.register("receipts", views.GoodsReceiptViewSet, basename="inventory-receipt")
router.register("purchases", views.DirectPurchaseViewSet, basename="inventory-purchase")
router.register("settings", views.InventorySettingsViewSet, basename="inventory-settings")
router.register("reports", views.InventoryReportViewSet, basename="inventory-report")

urlpatterns = router.urls
