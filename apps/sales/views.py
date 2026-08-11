from datetime import timedelta
from decimal import Decimal
import os

from django.db.models import Count, Prefetch, Q, Sum
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .debt_utils import apply_customer_debt_delta
from .models import (
    Customer,
    CustomerDebtPayment,
    Sale,
    SaleItem,
    SaleItemBatch,
    SaleReturn,
    SaleReturnItem,
)
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

    @action(detail=True, methods=["post"], url_path="pay-debt")
    def pay_debt(self, request, pk=None):
        """Qarzning bir qismini to'lash — qoldiq kamayadi."""
        tenant = request.user.tenant
        try:
            amount = Decimal(str(request.data.get("amount", "0")).replace(" ", "").replace(",", "."))
        except Exception:
            return Response({"detail": "Summa noto'g'ri."}, status=status.HTTP_400_BAD_REQUEST)
        if amount <= 0:
            return Response(
                {"detail": "To'lov summasi 0 dan katta bo'lishi kerak."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment_type = (request.data.get("payment_type") or "cash").strip().lower()
        if payment_type not in ("cash", "card"):
            payment_type = "cash"
        note = str(request.data.get("note") or "").strip()[:255]

        with transaction.atomic():
            customer = (
                Customer.objects.select_for_update()
                .filter(pk=pk, tenant=tenant)
                .first()
            )
            if not customer:
                return Response({"detail": "Mijoz topilmadi."}, status=status.HTTP_404_NOT_FOUND)

            current = customer.debt or Decimal("0")
            if current <= 0:
                return Response(
                    {"detail": "Bu mijozda qarz qoldig'i yo'q."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            paid = min(amount, current)
            balance = apply_customer_debt_delta(customer, -paid)

            last = (
                CustomerDebtPayment.objects.filter(tenant=tenant)
                .order_by("-receipt_number")
                .values_list("receipt_number", flat=True)
                .first()
            )
            receipt_number = (last or 0) + 1
            payment = CustomerDebtPayment.objects.create(
                tenant=tenant,
                customer=customer,
                user=request.user,
                amount=paid,
                payment_type=payment_type,
                note=note,
                receipt_number=receipt_number,
                balance_after=balance,
            )

        return Response(
            {
                "id": str(payment.id),
                "receipt_number": payment.receipt_number,
                "paid": str(paid),
                "debt_delta": str(-paid),
                "balance": str(balance),
                "balance_before": str(current),
                "payment_type": payment.payment_type,
                "check_path": f"/check/{tenant.server_name}/{payment.id}/",
                "check_url": f"{os.getenv('PUBLIC_CHECK_SITE_BASE', 'https://tez-pos.uz').rstrip('/')}/check/{tenant.server_name}/{payment.id}/",
                "customer": {
                    "id": str(customer.id),
                    "name": customer.name,
                    "phone": customer.phone or "",
                    "debt": str(balance),
                },
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
            }
        )


class SaleViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        items_qs = SaleItem.objects.order_by("sort_order", "id").prefetch_related(
            Prefetch(
                "batch_allocations",
                queryset=SaleItemBatch.objects.select_related("batch"),
            )
        )
        qs = (
            Sale.objects.filter(tenant=self.request.user.tenant)
            .prefetch_related(Prefetch("items", queryset=items_qs))
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
                qs = qs.filter(
                    Q(completed_at__date__gte=d)
                    | Q(completed_at__isnull=True, created_at__date__gte=d)
                )
        if date_to:
            d = parse_date(date_to)
            if d:
                qs = qs.filter(
                    Q(completed_at__date__lte=d)
                    | Q(completed_at__isnull=True, created_at__date__lte=d)
                )
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

    def perform_destroy(self, instance):
        from .stock import destroy_sale_with_stock

        destroy_sale_with_stock(instance)

    @action(detail=True, methods=["post"], url_path="print-receipt")
    def print_receipt(self, request, pk=None):
        sale = self.get_object()
        return Response(SaleSerializer(sale, context={"request": request}).data)


class SaleReturnViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        qs = (
            SaleReturn.objects.filter(tenant=self.request.user.tenant)
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=SaleReturnItem.objects.order_by("sort_order", "id"),
                )
            )
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

    def perform_destroy(self, instance):
        from .stock import destroy_return_with_stock

        destroy_return_with_stock(instance)


class SyncSalesView(APIView):
    """Offline sotuvlarni serverga yuborish — bitta xato butun navbatni to'xtatmasin."""

    def post(self, request):
        from apps.catalog.fifo import stock_snapshot
        from apps.catalog.models import Product
        from rest_framework.exceptions import ValidationError as DRFValidationError

        sales_data = request.data if isinstance(request.data, list) else [request.data]
        results = []
        failed = []
        touched_ids = set()

        for sale_data in sales_data:
            client_id = ""
            if isinstance(sale_data, dict):
                client_id = str(sale_data.get("client_id") or "")
            try:
                with transaction.atomic():
                    serializer = SyncSaleSerializer(
                        data=sale_data, context={"request": request}
                    )
                    serializer.is_valid(raise_exception=True)
                    sale = serializer.save()
                    if not sale.synced_at:
                        sale.synced_at = timezone.now()
                        sale.save(update_fields=["synced_at"])
                    for item in sale.items.all():
                        touched_ids.add(item.product_id)
                results.append(SaleListSerializer(sale).data)
            except DRFValidationError as exc:
                detail = exc.detail
                code = "error"
                available = None
                requested = None
                if isinstance(detail, dict):
                    code = detail.get("code") or code
                    available = detail.get("available")
                    requested = detail.get("requested")
                    msg = detail.get("detail") or detail
                else:
                    msg = detail
                failed.append(
                    {
                        "client_id": client_id,
                        "code": code,
                        "detail": msg if isinstance(msg, str) else str(msg),
                        "available": available,
                        "requested": requested,
                    }
                )
            except Exception as exc:
                failed.append(
                    {
                        "client_id": client_id,
                        "code": "error",
                        "detail": str(exc),
                    }
                )

        products = Product.objects.filter(id__in=touched_ids)
        return Response(
            {
                "synced": results,
                "failed": failed,
                "count": len(results),
                "stock_updates": stock_snapshot(products),
            }
        )


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


class TopProductsView(APIView):
    """Ko'p sotilgan mahsulotlar — barcha kassalar bo'yicha."""

    def get(self, request):
        days = min(max(int(request.query_params.get("days", 30)), 1), 365)
        limit = min(max(int(request.query_params.get("limit", 24)), 1), 100)
        since = timezone.now() - timedelta(days=days)
        rows = (
            SaleItem.objects.filter(
                sale__tenant=request.user.tenant,
                sale__status=Sale.STATUS_COMPLETED,
                sale__completed_at__gte=since,
            )
            .values("product_id")
            .annotate(
                quantity=Sum("quantity"),
                sales_count=Count("id"),
            )
            .order_by("-quantity", "-sales_count")[:limit]
        )
        return Response(
            {
                "days": days,
                "items": [
                    {
                        "product_id": str(row["product_id"]),
                        "quantity": float(row["quantity"] or 0),
                        "sales_count": row["sales_count"],
                    }
                    for row in rows
                ],
            }
        )
