from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

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

# DEBUG=false da django.conf.urls.static.static() hech narsa qo'shmaydi —
# shuning uchun media ni doim serve orqali ochiq qilamiz (gunicorn :8000).
urlpatterns += [
    re_path(
        r"^media/(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT},
    ),
]
