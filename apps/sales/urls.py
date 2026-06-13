from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CustomerViewSet,
    DailyStatsView,
    SaleReturnViewSet,
    SaleViewSet,
    SyncSalesView,
)

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("returns", SaleReturnViewSet, basename="return")
router.register("", SaleViewSet, basename="sale")

urlpatterns = [
    path("sync/", SyncSalesView.as_view()),
    path("stats/daily/", DailyStatsView.as_view()),
    path("", include(router.urls)),
]
