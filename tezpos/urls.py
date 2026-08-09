from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from apps.catalog.tenant_views import TenantProductListView
from apps.sales.public_check import PublicCheckJsonView, PublicCheckRedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    # HTML cheklar tezpos_site da — bu yerda redirect
    path(
        "check/<str:server_name>/<str:ref>/",
        PublicCheckRedirectView.as_view(),
        name="public-receipt-check",
    ),
    path(
        "check/<str:server_name>/<str:ref>",
        PublicCheckRedirectView.as_view(),
        name="public-receipt-check-noslash",
    ),
    # Sayt uchun JSON ma'lumot
    path(
        "api/public/check/<str:server_name>/<str:ref>/",
        PublicCheckJsonView.as_view(),
        name="public-check-json",
    ),
    path(
        "api/public/check/<str:server_name>/<str:ref>",
        PublicCheckJsonView.as_view(),
        name="public-check-json-noslash",
    ),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/catalog/", include("apps.catalog.urls")),
    path("api/products/", include("apps.catalog.product_barcode_lookup.urls")),
    path("api/sales/", include("apps.sales.urls")),
    path("api/external/", include("apps.catalog.external_urls")),
    path("<str:server_name>/product/", TenantProductListView.as_view(), name="tenant-products"),
]

urlpatterns += [
    re_path(
        r"^media/(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT},
    ),
]
