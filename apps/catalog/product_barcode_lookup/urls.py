from django.urls import path

from .views import ProductBarcodeLookupView

urlpatterns = [
    path(
        "barcode/<str:barcode>/",
        ProductBarcodeLookupView.as_view(),
        name="product-barcode-lookup",
    ),
]
