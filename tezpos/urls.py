from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.catalog.tenant_views import TenantProductListView
from apps.sales.public_check import PublicReceiptCheckView

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "check/<str:server_name>/<int:receipt_number>/",
        PublicReceiptCheckView.as_view(),
        name="public-receipt-check",
    ),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/catalog/", include("apps.catalog.urls")),
    path("api/products/", include("apps.catalog.product_barcode_lookup.urls")),
    path("api/sales/", include("apps.sales.urls")),
    path("api/external/", include("apps.catalog.external_urls")),
    path("<str:server_name>/product/", TenantProductListView.as_view(), name="tenant-products"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
