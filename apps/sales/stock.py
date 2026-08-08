"""Ombordagi qoldiq — Kirim / Sotuv / Qaytarish / Reviziya (FIFO partiyalar).

Haqiqiy manba: StockBatch.qty_remaining
Product.quantity — cache (fifo.sync_product_quantity).
"""

from __future__ import annotations

from django.db import transaction

from apps.catalog.fifo import restore_sale_allocations, reverse_return_batches

from .debt_utils import apply_customer_debt_delta
from .models import Sale, SaleReturn


def restore_stock_for_sale(sale: Sale) -> None:
    """Completed sotuv o'chirilganda — partiyalarga FIFO snapshot bo'yicha qaytarish."""
    restore_sale_allocations(sale)
    if sale.customer_id and sale.debt_amount and sale.debt_amount > 0:
        apply_customer_debt_delta(sale.customer, -sale.debt_amount)


def reverse_stock_for_return(sale_return: SaleReturn) -> None:
    """Completed qaytarish o'chirilganda — qaytarish partiyalarini bekor qilish."""
    reverse_return_batches(sale_return)
    if (
        sale_return.customer_id
        and sale_return.debt_amount
        and sale_return.debt_amount > 0
    ):
        apply_customer_debt_delta(sale_return.customer, sale_return.debt_amount)


@transaction.atomic
def destroy_sale_with_stock(sale: Sale) -> None:
    restore_stock_for_sale(sale)
    sale.delete()


@transaction.atomic
def destroy_return_with_stock(sale_return: SaleReturn) -> None:
    reverse_stock_for_return(sale_return)
    sale_return.delete()
