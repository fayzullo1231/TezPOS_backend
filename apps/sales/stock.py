"""Ombordagi qoldiq — Kirim / Sotuv / Qaytarish / Reviziya (include_stock).

Sotuv yaratilganda qoldiq kamayadi; sotuv o'chirilganda (savatga qaytarish)
qoldiq qaytariladi. Qaytarish yaratilganda qo'shiladi; o'chirilganda ayiriladi.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import F

from apps.catalog.models import Product

from .debt_utils import apply_customer_debt_delta
from .models import Sale, SaleReturn


def restore_stock_for_sale(sale: Sale) -> None:
    """Completed sotuv o'chirilganda omborga qaytarish."""
    if sale.status != Sale.STATUS_COMPLETED:
        return
    for item in sale.items.all():
        product = Product.objects.select_for_update().get(pk=item.product_id)
        product.quantity = F("quantity") + item.quantity
        product.save(update_fields=["quantity", "updated_at"])
    if sale.customer_id and sale.debt_amount and sale.debt_amount > 0:
        apply_customer_debt_delta(sale.customer, -sale.debt_amount)


def reverse_stock_for_return(sale_return: SaleReturn) -> None:
    """Completed qaytarish o'chirilganda ombordan qaytarilgan miqdorni ayirish."""
    if sale_return.status != SaleReturn.STATUS_COMPLETED:
        return
    for item in sale_return.items.all():
        product = Product.objects.select_for_update().get(pk=item.product_id)
        product.quantity = F("quantity") - item.quantity
        product.save(update_fields=["quantity", "updated_at"])
    if (
        sale_return.customer_id
        and sale_return.debt_amount
        and sale_return.debt_amount > 0
    ):
        # Qaytarish qarzni kamaytirgan edi — o'chirishda qarzni qayta qo'shamiz
        apply_customer_debt_delta(sale_return.customer, sale_return.debt_amount)


@transaction.atomic
def destroy_sale_with_stock(sale: Sale) -> None:
    restore_stock_for_sale(sale)
    sale.delete()


@transaction.atomic
def destroy_return_with_stock(sale_return: SaleReturn) -> None:
    reverse_stock_for_return(sale_return)
    sale_return.delete()
