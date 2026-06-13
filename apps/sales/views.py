from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customer, Sale, SaleReturn
from .return_serializers import (
    SaleReturnListSerializer,
    SaleReturnSerializer,
)
from .serializers import (
    CustomerSerializer,
    SaleListSerializer,
    SaleSerializer,
    SyncSaleSerializer,
)


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer

    def get_queryset(self):
        return Customer.objects.filter(tenant=self.request.user.tenant)

    def paginate_queryset(self, queryset):
        if self.action == "list" and self.request.query_params.get("all") == "true":
            return None
        return super().paginate_queryset(queryset)

    def get_serializer_context(self):
        return {"request": self.request}


class SaleViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        qs = (
            Sale.objects.filter(tenant=self.request.user.tenant)
            .prefetch_related("items")
            .select_related("customer", "user")
        )
        params = self.request.query_params
        search = params.get("search", "").strip()
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        synced = params.get("synced")

        if search:
            q = Q(customer_name__icontains=search) | Q(comment__icontains=search)
            if search.isdigit():
                q |= Q(receipt_number=int(search))
            qs = qs.filter(q)
        if date_from:
            d = parse_date(date_from)
            if d:
                qs = qs.filter(completed_at__date__gte=d)
        if date_to:
            d = parse_date(date_to)
            if d:
                qs = qs.filter(completed_at__date__lte=d)
        if synced == "true":
            qs = qs.exclude(synced_at__isnull=True)
        elif synced == "false":
            qs = qs.filter(synced_at__isnull=True)

        return qs.filter(status=Sale.STATUS_COMPLETED)

    def paginate_queryset(self, queryset):
        if self.action == "list" and self.request.query_params.get("all") == "true":
            return None
        return super().paginate_queryset(queryset)

    def get_serializer_class(self):
        if self.action == "list":
            return SaleListSerializer
        return SaleSerializer

    def get_serializer_context(self):
        return {"request": self.request}

    def perform_create(self, serializer):
        shift = (
            self.request.user.shifts.filter(status="open").order_by("-opened_at").first()
        )
        serializer.save(user=self.request.user, shift=shift)

    @action(detail=True, methods=["post"], url_path="print-receipt")
    def print_receipt(self, request, pk=None):
        sale = self.get_object()
        return Response(SaleSerializer(sale, context={"request": request}).data)


class SaleReturnViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        qs = (
            SaleReturn.objects.filter(tenant=self.request.user.tenant)
            .prefetch_related("items")
            .select_related("customer", "user")
        )
        params = self.request.query_params
        search = params.get("search", "").strip()
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        synced = params.get("synced")

        if search:
            q = Q(customer_name__icontains=search) | Q(comment__icontains=search)
            if search.isdigit():
                q |= Q(receipt_number=int(search))
            qs = qs.filter(q)
        if date_from:
            d = parse_date(date_from)
            if d:
                qs = qs.filter(completed_at__date__gte=d)
        if date_to:
            d = parse_date(date_to)
            if d:
                qs = qs.filter(completed_at__date__lte=d)
        if synced == "true":
            qs = qs.exclude(synced_at__isnull=True)
        elif synced == "false":
            qs = qs.filter(synced_at__isnull=True)

        return qs.filter(status=SaleReturn.STATUS_COMPLETED)

    def paginate_queryset(self, queryset):
        if self.action == "list" and self.request.query_params.get("all") == "true":
            return None
        return super().paginate_queryset(queryset)

    def get_serializer_class(self):
        if self.action == "list":
            return SaleReturnListSerializer
        return SaleReturnSerializer

    def get_serializer_context(self):
        return {"request": self.request}

    def perform_create(self, serializer):
        shift = (
            self.request.user.shifts.filter(status="open").order_by("-opened_at").first()
        )
        serializer.save(user=self.request.user, shift=shift)


class SyncSalesView(APIView):
    """Offline sotuvlarni serverga yuborish."""

    def post(self, request):
        sales_data = request.data if isinstance(request.data, list) else [request.data]
        results = []
        for sale_data in sales_data:
            serializer = SyncSaleSerializer(data=sale_data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            sale = serializer.save()
            sale.synced_at = timezone.now()
            sale.save(update_fields=["synced_at"])
            results.append(SaleListSerializer(sale).data)
        return Response({"synced": results, "count": len(results)})


class DailyStatsView(APIView):
    def get(self, request):
        today = timezone.localdate()
        qs = Sale.objects.filter(
            tenant=request.user.tenant,
            status=Sale.STATUS_COMPLETED,
            completed_at__date=today,
        )
        agg = qs.aggregate(total_sales=Sum("total"), count=Sum("id"))
        return Response(
            {
                "date": str(today),
                "sales_count": qs.count(),
                "total_revenue": agg["total_sales"] or 0,
            }
        )
