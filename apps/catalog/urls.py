from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .barcode_external_views import ExternalBarcodeLookupView
from .inventory_views import PriceListViewSet, StockAuditViewSet, StockReceiptViewSet
from .views import (
    BrandViewSet,
    CategoryViewSet,
    ProductViewSet,
    SupplierViewSet,
    UnitOfMeasureViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("units", UnitOfMeasureViewSet, basename="unit")
router.register("products", ProductViewSet, basename="product")
router.register("price-lists", PriceListViewSet, basename="price-list")
router.register("stock-receipts", StockReceiptViewSet, basename="stock-receipt")
router.register("stock-audits", StockAuditViewSet, basename="stock-audit")

urlpatterns = [
    path("barcode-lookup/", ExternalBarcodeLookupView.as_view(), name="barcode-lookup"),
    path("", include(router.urls)),
]
