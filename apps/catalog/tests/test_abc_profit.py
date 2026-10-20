"""ABC foyda: FIFO, minus qoldiq, bonus kirim, chek chegirmasi, qaytarish."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.catalog.fifo import consume_fifo, create_batch
from apps.catalog.models import Product, StockBatch, StockReceipt, StockReceiptItem
from apps.sales.abc_analysis import build_abc_payload
from apps.sales.models import Sale, SaleItem, SaleReturn, SaleReturnItem

User = get_user_model()


def D(v):
    return Decimal(str(v))


class AbcProfitTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(server_name="abc-t", display_name="ABC", is_active=True)
        self.user = User.objects.create_user(username="abc_u", password="x", tenant=self.tenant)
        self.p = Product.objects.create(
            tenant=self.tenant, name="A", price=D(150), cost_price=D(100), quantity=D(0)
        )
        self.today = timezone.localdate()

    def _sale(self, lines, discount=0):
        sub = sum((D(q) * D(pr) for q, pr in lines), D(0))
        sale = Sale.objects.create(
            tenant=self.tenant,
            user=self.user,
            status=Sale.STATUS_COMPLETED,
            subtotal=sub,
            discount_amount=D(discount),
            total=sub - D(discount),
            completed_at=timezone.now(),
        )
        for q, pr in lines:
            it = SaleItem.objects.create(
                sale=sale,
                product=self.p,
                product_name="A",
                quantity=D(q),
                unit_price=D(pr),
                total=D(q) * D(pr),
            )
            consume_fifo(self.p, D(q), sale_item=it, allow_negative=True)
        return sale

    def _abc(self):
        data = build_abc_payload(self.tenant, date_from=self.today, date_to=self.today)
        row = next(x for x in data["items"] if x["product_id"] == str(self.p.id))
        return row, data["summary"]

    def test_fifo_cost(self):
        create_batch(self.p, D(10), D(100), source_type=StockBatch.SOURCE_RECEIPT)
        self._sale([(4, 150)])
        row, _ = self._abc()
        self.assertEqual(row["sales"], 600.0)
        self.assertEqual(row["cost"], 400.0)
        self.assertEqual(row["profit"], 200.0)

    def test_oversold_part_uses_cost_price(self):
        create_batch(self.p, D(2), D(100), source_type=StockBatch.SOURCE_RECEIPT)
        self._sale([(5, 150)])
        row, _ = self._abc()
        self.assertEqual(row["cost"], 500.0)
        self.assertEqual(row["profit"], 250.0)

    def test_bonus_is_full_profit(self):
        rc = StockReceipt.objects.create(
            tenant=self.tenant, payment_type="bonus", completed_at=timezone.now()
        )
        ri = StockReceiptItem.objects.create(
            receipt=rc, product=self.p, product_name="A", quantity=D(3), cost_price=D(0)
        )
        create_batch(
            self.p, D(3), D(0), source_type=StockBatch.SOURCE_RECEIPT, receipt_item=ri
        )
        self._sale([(3, 150)])
        row, _ = self._abc()
        self.assertEqual(row["cost"], 0.0)
        self.assertEqual(row["profit"], 450.0)

    def test_zero_cost_audit_batch_uses_cost_price(self):
        create_batch(self.p, D(3), D(0), source_type=StockBatch.SOURCE_AUDIT)
        self._sale([(3, 150)])
        row, _ = self._abc()
        self.assertEqual(row["cost"], 300.0)

    def test_check_discount_and_return(self):
        create_batch(self.p, D(10), D(100), source_type=StockBatch.SOURCE_RECEIPT)
        self._sale([(4, 150)], discount=100)
        ret = SaleReturn.objects.create(
            tenant=self.tenant,
            status=SaleReturn.STATUS_COMPLETED,
            subtotal=D(150),
            total=D(150),
            completed_at=timezone.now(),
        )
        SaleReturnItem.objects.create(
            sale_return=ret, product=self.p, product_name="A", quantity=D(1), unit_price=D(150), total=D(150)
        )
        row, s = self._abc()
        self.assertEqual(row["qty"], 3.0)
        self.assertEqual(row["sales"], 350.0)
        self.assertEqual(row["cost"], 300.0)
        self.assertEqual(row["profit"], 50.0)
        self.assertEqual(s["total_profit"], 50.0)
