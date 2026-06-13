from django.urls import path

from .external_views import ExternalProductCreateView, ExternalProductListView

urlpatterns = [
    path("products/", ExternalProductListView.as_view()),
    path("products/create/", ExternalProductCreateView.as_view()),
]
