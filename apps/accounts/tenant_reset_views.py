from decimal import Decimal

from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import (
    Product,
    StockAudit,
    StockAuditItem,
    StockReceipt,
    StockReceiptItem,
)
from apps.sales.models import (
    Customer,
    CustomerDebtPayment,
    Sale,
    SaleItem,
    SaleReturn,
    SaleReturnItem,
)

from .models import CashTransaction, Shift
from .permissions import IsTenantAdmin


class TenantResetView(APIView):
    """Tenant ma'lumotlarini alohida tozalash (faqat admin)."""

    permission_classes = [IsAuthenticated, IsTenantAdmin]

    ACTIONS = frozenset(
        {
            "sales",
            "stock_qty",
            "stock_docs",
            "shifts",
            "customer_debts",
            "products",
            "all",
        }
    )

    MESSAGES = {
        "sales": "Sotuv va qaytarishlar tozalandi.",
        "stock_qty": "Ombor qoldiqlari 0 ga tushirildi.",
        "stock_docs": "Kirim va reviziya hujjatlari tozalandi.",
        "shifts": "Smena va kassa tarixi tozalandi.",
        "customer_debts": "Mijoz qarzlari 0 ga tushirildi.",
        "products": "Barcha mahsulotlar o'chirildi.",
        "all": "Barcha tranzaksiyalar tozalandi, qoldiqlar 0 ga tushirildi.",
    }

    def post(self, request):
        action = (request.data.get("action") or "").strip().lower()
        if action not in self.ACTIONS:
            return Response(
                {
                    "detail": f"Noto'g'ri action. Ruxsat etilgan: {', '.join(sorted(self.ACTIONS))}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant = request.user.tenant
        if not tenant:
            return Response(
                {"detail": "Tenant topilmadi."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            counts = self._run(tenant, action)
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Ba'zi yozuvlar bog'liqligi sabab o'chirilmadi. "
                        "Avval «Sotuv va qaytarishlarni tozalash» yoki "
                        "«Barcha tranzaksiyalarni tozalash» ni bosing."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {"detail": f"Tozalash xatosi: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "action": action,
                "message": self.MESSAGES.get(action, "Tozalandi."),
                "counts": counts,
                "deleted_sales": counts.get("sales", 0),
                "deleted_returns": counts.get("returns", 0),
            }
        )

    @transaction.atomic
    def _run(self, tenant, action: str) -> dict:
        counts: dict = {}
        tid = tenant.id

        if action in ("sales", "all", "products"):
            counts["sales"] = Sale.objects.filter(tenant_id=tid).count()
            counts["returns"] = SaleReturn.objects.filter(tenant_id=tid).count()
            # Tez bulk delete (CASCADE collector sekin)
            SaleItem.objects.filter(sale__tenant_id=tid)._raw_delete(
                SaleItem.objects.db
            )
            SaleReturnItem.objects.filter(sale_return__tenant_id=tid)._raw_delete(
                SaleReturnItem.objects.db
            )
            Sale.objects.filter(tenant_id=tid)._raw_delete(Sale.objects.db)
            SaleReturn.objects.filter(tenant_id=tid)._raw_delete(SaleReturn.objects.db)

        if action in ("stock_docs", "all", "products"):
            counts["stock_receipts"] = StockReceipt.objects.filter(tenant_id=tid).count()
            counts["stock_audits"] = StockAudit.objects.filter(tenant_id=tid).count()
            StockReceiptItem.objects.filter(receipt__tenant_id=tid)._raw_delete(
                StockReceiptItem.objects.db
            )
            StockAuditItem.objects.filter(audit__tenant_id=tid)._raw_delete(
                StockAuditItem.objects.db
            )
            StockReceipt.objects.filter(tenant_id=tid)._raw_delete(StockReceipt.objects.db)
            StockAudit.objects.filter(tenant_id=tid)._raw_delete(StockAudit.objects.db)

        if action in ("shifts", "all"):
            counts["cash_transactions"] = CashTransaction.objects.filter(
                tenant_id=tid
            ).count()
            counts["shifts"] = Shift.objects.filter(tenant_id=tid).count()
            CashTransaction.objects.filter(tenant_id=tid)._raw_delete(
                CashTransaction.objects.db
            )
            Shift.objects.filter(tenant_id=tid)._raw_delete(Shift.objects.db)

        if action in ("stock_qty", "all"):
            products = Product.objects.filter(tenant_id=tid).count()
            zeroed = Product.objects.filter(tenant_id=tid).update(quantity=Decimal("0"))
            counts["products_zeroed"] = zeroed
            counts["products_total"] = products

        if action in ("customer_debts", "all"):
            CustomerDebtPayment.objects.filter(tenant_id=tid)._raw_delete(
                CustomerDebtPayment.objects.db
            )
            counts["customers_debt_zeroed"] = Customer.objects.filter(
                tenant_id=tid
            ).update(debt=Decimal("0"))

        if action == "products":
            # Sotuv/kirim bog'liqligi yuqorida tozalandi
            counts["products_deleted"] = Product.objects.filter(tenant_id=tid).count()
            Product.objects.filter(tenant_id=tid).delete()

        return counts
