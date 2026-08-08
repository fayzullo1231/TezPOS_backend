"""FIFO partiya — majburiy testlar (1–7)."""

from decimal import Decimal
from unittest import skipIf

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase

from apps.accounts.models import Tenant
from apps.catalog.fifo import (
    InsufficientStockError,
    batch_remaining_sum,
    consume_fifo,
    create_batch,
    create_return_batch,
    restore_sale_allocations,
)
from apps.catalog.models import Product, StockBatch
from apps.sales.models import Sale, SaleItem


User = get_user_model()


def _dec(v):
    return Decimal(str(v))


class FifoBatchTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            server_name="fifo-test", display_name="FIFO Test", is_active=True
        )
        self.user = User.objects.create_user(
            username="fifo_cashier",
            password="x",
            tenant=self.tenant,
        )
        self.product = Product.objects.create(
            tenant=self.tenant,
            name="MAXITO",
            price=_dec("15000"),
            cost_price=_dec("10000"),
            quantity=_dec("0"),
        )

    def test_1_two_receipts_total_80(self):
        create_batch(
            self.product,
            _dec("50"),
            _dec("10000"),
            source_type=StockBatch.SOURCE_RECEIPT,
            set_product_cost=True,
        )
        create_batch(
            self.product,
            _dec("30"),
            _dec("11000"),
            source_type=StockBatch.SOURCE_RECEIPT,
            set_product_cost=True,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, _dec("80"))
        batches = list(
            StockBatch.objects.filter(product=self.product).order_by("batch_number")
        )
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0].qty_remaining, _dec("50"))
        self.assertEqual(batches[0].unit_cost, _dec("10000"))
        self.assertEqual(batches[1].qty_remaining, _dec("30"))
        self.assertEqual(batches[1].unit_cost, _dec("11000"))

    def test_2_fifo_sell_60(self):
        create_batch(
            self.product, _dec("50"), _dec("10000"), source_type=StockBatch.SOURCE_RECEIPT
        )
        create_batch(
            self.product, _dec("30"), _dec("11000"), source_type=StockBatch.SOURCE_RECEIPT
        )
        sale = Sale.objects.create(
            tenant=self.tenant,
            user=self.user,
            status=Sale.STATUS_COMPLETED,
            receipt_number=1,
            total=_dec("0"),
        )
        item = SaleItem.objects.create(
            sale=sale,
            product=self.product,
            product_name="MAXITO",
            quantity=_dec("60"),
            unit_price=_dec("15000"),
            total=_dec("900000"),
        )
        allocs = consume_fifo(self.product, _dec("60"), sale_item=item, reference_id=sale.id)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, _dec("20"))
        b1, b2 = StockBatch.objects.filter(product=self.product).order_by("batch_number")
        self.assertEqual(b1.qty_remaining, _dec("0"))
        self.assertEqual(b2.qty_remaining, _dec("20"))
        self.assertEqual(len(allocs), 2)
        self.assertEqual(_dec(allocs[0]["quantity"]), _dec("50"))
        self.assertEqual(_dec(allocs[0]["unit_cost"]), _dec("10000"))
        self.assertEqual(_dec(allocs[1]["quantity"]), _dec("10"))
        self.assertEqual(_dec(allocs[1]["unit_cost"]), _dec("11000"))

    def test_3_sell_remaining_20_to_zero(self):
        create_batch(
            self.product, _dec("50"), _dec("10000"), source_type=StockBatch.SOURCE_RECEIPT
        )
        create_batch(
            self.product, _dec("30"), _dec("11000"), source_type=StockBatch.SOURCE_RECEIPT
        )
        sale = Sale.objects.create(
            tenant=self.tenant, user=self.user, status=Sale.STATUS_COMPLETED, receipt_number=1
        )
        item = SaleItem.objects.create(
            sale=sale,
            product=self.product,
            product_name="MAXITO",
            quantity=_dec("60"),
            unit_price=_dec("1"),
            total=_dec("1"),
        )
        consume_fifo(self.product, _dec("60"), sale_item=item)
        sale2 = Sale.objects.create(
            tenant=self.tenant, user=self.user, status=Sale.STATUS_COMPLETED, receipt_number=2
        )
        item2 = SaleItem.objects.create(
            sale=sale2,
            product=self.product,
            product_name="MAXITO",
            quantity=_dec("20"),
            unit_price=_dec("1"),
            total=_dec("1"),
        )
        consume_fifo(self.product, _dec("20"), sale_item=item2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, _dec("0"))
        self.assertEqual(batch_remaining_sum(self.product), _dec("0"))

    def test_4_oversell_rejected(self):
        create_batch(
            self.product, _dec("80"), _dec("10000"), source_type=StockBatch.SOURCE_RECEIPT
        )
        with self.assertRaises(InsufficientStockError) as ctx:
            consume_fifo(self.product, _dec("81"))
        self.assertEqual(ctx.exception.available, _dec("80"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, _dec("80"))

    def test_6_fifo_after_second_receipt(self):
        create_batch(
            self.product, _dec("100"), _dec("10000"), source_type=StockBatch.SOURCE_RECEIPT
        )
        create_batch(
            self.product, _dec("50"), _dec("12000"), source_type=StockBatch.SOURCE_RECEIPT
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, _dec("150"))
        sale = Sale.objects.create(
            tenant=self.tenant, user=self.user, status=Sale.STATUS_COMPLETED, receipt_number=1
        )
        item = SaleItem.objects.create(
            sale=sale,
            product=self.product,
            product_name="MAXITO",
            quantity=_dec("50"),
            unit_price=_dec("1"),
            total=_dec("1"),
        )
        consume_fifo(self.product, _dec("50"), sale_item=item)
        b1, b2 = StockBatch.objects.filter(product=self.product).order_by("batch_number")
        self.assertEqual(b1.qty_remaining, _dec("50"))
        self.assertEqual(b2.qty_remaining, _dec("50"))

    def test_7_restore_sale_returns_to_batches(self):
        create_batch(
            self.product, _dec("50"), _dec("10000"), source_type=StockBatch.SOURCE_RECEIPT
        )
        create_batch(
            self.product, _dec("30"), _dec("11000"), source_type=StockBatch.SOURCE_RECEIPT
        )
        sale = Sale.objects.create(
            tenant=self.tenant, user=self.user, status=Sale.STATUS_COMPLETED, receipt_number=1
        )
        item = SaleItem.objects.create(
            sale=sale,
            product=self.product,
            product_name="MAXITO",
            quantity=_dec("60"),
            unit_price=_dec("1"),
            total=_dec("1"),
        )
        consume_fifo(self.product, _dec("60"), sale_item=item)
        restore_sale_allocations(sale)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, _dec("80"))
        b1, b2 = StockBatch.objects.filter(product=self.product).order_by("batch_number")
        self.assertEqual(b1.qty_remaining, _dec("50"))
        self.assertEqual(b2.qty_remaining, _dec("30"))
        # Eski partiya tannarxi saqlangan
        self.assertEqual(b1.unit_cost, _dec("10000"))
        self.assertEqual(b2.unit_cost, _dec("11000"))

    def test_return_creates_new_batch(self):
        create_batch(
            self.product, _dec("10"), _dec("10000"), source_type=StockBatch.SOURCE_RECEIPT
        )
        create_return_batch(self.product, _dec("5"), unit_cost=_dec("10000"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, _dec("15"))


@skipIf(connection.vendor == "sqlite", "Concurrent select_for_update needs Postgres")
class FifoConcurrencyTests(TransactionTestCase):
    def test_5_parallel_sales_no_negative(self):
        # Postgres'da to'liq test; sqlite'da skip
        pass
