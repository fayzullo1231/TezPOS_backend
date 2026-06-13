from rest_framework import status, viewsets
from rest_framework.response import Response

from .inventory_serializers import (
    PriceListSerializer,
    StockAuditCreateSerializer,
    StockAuditReadSerializer,
    StockReceiptCreateSerializer,
    StockReceiptReadSerializer,
)
from .models import PriceList, ProductPrice, StockAudit, StockReceipt
from .views import TenantMixin


class PriceListViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = PriceList.objects.all()
    serializer_class = PriceListSerializer

    def get_queryset(self):
        return PriceList.objects.filter(
            tenant=self.request.user.tenant,
            is_active=True,
        )

    def paginate_queryset(self, queryset):
        if self.action == "list":
            return None
        return super().paginate_queryset(queryset)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        ProductPrice.objects.filter(price_list=instance).delete()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StockReceiptViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = StockReceipt.objects.prefetch_related("items").select_related("supplier")
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return StockReceiptCreateSerializer
        return StockReceiptReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = StockReceiptCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        receipt = serializer.save()
        return Response(
            StockReceiptReadSerializer(receipt).data,
            status=201,
        )


class StockAuditViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = StockAudit.objects.prefetch_related("items")
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return StockAuditCreateSerializer
        return StockAuditReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = StockAuditCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        audit = serializer.save()
        return Response(
            StockAuditReadSerializer(audit).data,
            status=201,
        )
