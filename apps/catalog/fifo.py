"""FIFO partiya ombori — Single Source of Truth: StockBatch.qty_remaining.

Product.quantity — tezkor cache; har bir kirim/sotuv/return/audit dan keyin
partiyalar yig'indisiga sinxronlanadi.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Product, StockBatch, StockMovement


ZERO = Decimal("0")
Q3 = Decimal("0.001")


class InsufficientStockError(Exception):
    def __init__(self, product: Product, available: Decimal, requested: Decimal):
        self.product = product
        self.available = available
        self.requested = requested
        name = getattr(product, "name", "") or "Mahsulot"
        super().__init__(
            f"Omborda yetarli mahsulot mavjud emas.\n"
            f"Mahsulot: {name}\n"
            f"Mavjud: {available} dona\n"
            f"So'ralgan: {requested} dona"
        )

    def as_validation_error(self) -> ValidationError:
        return ValidationError(
            {
                "detail": str(self),
                "code": "insufficient_stock",
                "product_id": str(self.product.id),
                "product_name": self.product.name,
                "available": str(self.available),
                "requested": str(self.requested),
            }
        )


def _d(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def batch_remaining_sum(product: Product) -> Decimal:
    total = (
        StockBatch.objects.filter(product_id=product.pk, qty_remaining__gt=0).aggregate(
            s=Sum("qty_remaining")
        )["s"]
    )
    return _d(total)


def sync_product_quantity(product: Product, *, also_cost_from_newest: bool = False) -> Decimal:
    """Product.quantity = SUM(aktiv partiya qoldiqlari)."""
    total = batch_remaining_sum(product)
    update_fields = ["quantity", "updated_at"]
    product.quantity = total
    if also_cost_from_newest:
        newest = (
            StockBatch.objects.filter(product_id=product.pk, qty_remaining__gt=0)
            .order_by("-received_at", "-batch_number")
            .only("unit_cost")
            .first()
        )
        if newest is not None:
            product.cost_price = newest.unit_cost
            update_fields.append("cost_price")
    product.save(update_fields=update_fields)
    return total


def next_batch_number(tenant_id) -> int:
    last = (
        StockBatch.objects.filter(tenant_id=tenant_id)
        .aggregate(m=Max("batch_number"))["m"]
        or 0
    )
    return int(last) + 1


def _log_movement(
    *,
    tenant,
    product: Product,
    batch: StockBatch | None,
    movement_type: str,
    quantity: Decimal,
    unit_cost: Decimal,
    reference_type: str = "",
    reference_id=None,
    note: str = "",
) -> StockMovement:
    return StockMovement.objects.create(
        tenant=tenant,
        product=product,
        batch=batch,
        movement_type=movement_type,
        quantity=quantity,
        unit_cost=unit_cost,
        reference_type=reference_type or "",
        reference_id=reference_id,
        note=note or "",
    )


@transaction.atomic
def create_batch(
    product: Product,
    quantity: Decimal,
    unit_cost: Decimal,
    *,
    source_type: str,
    source_id=None,
    receipt_item=None,
    received_at=None,
    note: str = "",
    set_product_cost: bool = False,
) -> StockBatch:
    """Yangi kirim/qaytarish/reviziya partiyasi. Eski partiyalar o'zgarmaydi."""
    qty = _d(quantity)
    cost = _d(unit_cost)
    if qty <= ZERO:
        raise ValidationError({"quantity": "Miqdor 0 dan katta bo'lishi kerak."})

    product = Product.objects.select_for_update().get(pk=product.pk)
    batch = StockBatch.objects.create(
        tenant_id=product.tenant_id,
        product=product,
        batch_number=next_batch_number(product.tenant_id),
        qty_received=qty,
        qty_remaining=qty,
        unit_cost=cost,
        received_at=received_at or timezone.now(),
        source_type=source_type,
        source_id=source_id,
        receipt_item=receipt_item,
        note=note or "",
    )
    move_type = {
        StockBatch.SOURCE_RECEIPT: StockMovement.TYPE_RECEIPT,
        StockBatch.SOURCE_RETURN: StockMovement.TYPE_RETURN,
        StockBatch.SOURCE_AUDIT: StockMovement.TYPE_AUDIT,
        StockBatch.SOURCE_OPENING: StockMovement.TYPE_OPENING,
        StockBatch.SOURCE_ADJUSTMENT: StockMovement.TYPE_ADJUSTMENT,
    }.get(source_type, StockMovement.TYPE_RECEIPT)

    _log_movement(
        tenant=product.tenant,
        product=product,
        batch=batch,
        movement_type=move_type,
        quantity=qty,
        unit_cost=cost,
        reference_type=source_type,
        reference_id=source_id or (receipt_item.id if receipt_item else None),
        note=note,
    )

    if set_product_cost:
        product.cost_price = cost
        product.save(update_fields=["cost_price", "updated_at"])

    sync_product_quantity(product)
    return batch


@transaction.atomic
def consume_fifo(
    product: Product,
    quantity: Decimal,
    *,
    sale_item=None,
    reference_type: str = "sale",
    reference_id=None,
    allow_negative: bool = False,
) -> list[dict]:
    """FIFO: eng eski partiyadan sarflash. SaleItemBatch yozuvlari yaratiladi."""
    from apps.sales.models import SaleItemBatch

    qty = _d(quantity)
    if qty <= ZERO:
        return []

    product = Product.objects.select_for_update().get(pk=product.pk)
    batches = list(
        StockBatch.objects.select_for_update()
        .filter(product_id=product.pk, qty_remaining__gt=0)
        .order_by("received_at", "batch_number", "created_at")
    )
    available = sum((_d(b.qty_remaining) for b in batches), ZERO)

    if not allow_negative and qty > available:
        raise InsufficientStockError(product, available, qty)

    remaining = qty
    allocations: list[dict] = []

    for batch in batches:
        if remaining <= ZERO:
            break
        take = min(_d(batch.qty_remaining), remaining)
        if take <= ZERO:
            continue
        batch.qty_remaining = _d(batch.qty_remaining) - take
        batch.save(update_fields=["qty_remaining", "updated_at"])

        if sale_item is not None:
            SaleItemBatch.objects.create(
                sale_item=sale_item,
                batch=batch,
                quantity=take,
                unit_cost=batch.unit_cost,
            )

        _log_movement(
            tenant=product.tenant,
            product=product,
            batch=batch,
            movement_type=StockMovement.TYPE_SALE,
            quantity=take,
            unit_cost=batch.unit_cost,
            reference_type=reference_type,
            reference_id=reference_id or (sale_item.id if sale_item else None),
        )
        allocations.append(
            {
                "batch_id": str(batch.id),
                "batch_number": batch.batch_number,
                "quantity": str(take),
                "unit_cost": str(batch.unit_cost),
            }
        )
        remaining -= take

    if remaining > ZERO and allow_negative:
        # Faqat favqulodda — yangi manfiy partiya yaratilmaydi; product sync 0 ga tushadi
        pass

    sync_product_quantity(product)
    return allocations


@transaction.atomic
def restore_sale_allocations(sale) -> None:
    """Sotuv bekor/o'chirilganda — partiyalarga qaytarish (tarixiy tannarx saqlanadi)."""
    from apps.sales.models import SaleItemBatch

    if sale.status != sale.STATUS_COMPLETED:
        return

    items = list(sale.items.select_related("product").prefetch_related("batch_allocations"))
    touched: dict = {}

    for item in items:
        allocs = list(item.batch_allocations.select_related("batch"))
        if allocs:
            for alloc in allocs:
                batch = StockBatch.objects.select_for_update().get(pk=alloc.batch_id)
                batch.qty_remaining = _d(batch.qty_remaining) + _d(alloc.quantity)
                batch.save(update_fields=["qty_remaining", "updated_at"])
                product = Product.objects.select_for_update().get(pk=item.product_id)
                _log_movement(
                    tenant=product.tenant,
                    product=product,
                    batch=batch,
                    movement_type=StockMovement.TYPE_SALE_CANCEL,
                    quantity=_d(alloc.quantity),
                    unit_cost=alloc.unit_cost,
                    reference_type="sale",
                    reference_id=sale.id,
                )
                touched[product.pk] = product
        else:
            # Migratsiyadan oldingi sotuv — yangi adjustment partiya
            product = Product.objects.select_for_update().get(pk=item.product_id)
            create_batch(
                product,
                _d(item.quantity),
                _d(product.cost_price),
                source_type=StockBatch.SOURCE_ADJUSTMENT,
                source_id=sale.id,
                note=f"Sotuv #{sale.receipt_number} bekor (eski yozuv)",
                set_product_cost=False,
            )
            touched[product.pk] = product

    for product in touched.values():
        sync_product_quantity(product)


@transaction.atomic
def create_return_batch(
    product: Product,
    quantity: Decimal,
    *,
    return_item=None,
    unit_cost: Decimal | None = None,
    reference_id=None,
) -> StockBatch:
    """Qaytarish — yangi partiya (agar asl sotuv partiyasi bog'lanmagan)."""
    from apps.sales.models import SaleReturnItemBatch

    product = Product.objects.select_for_update().get(pk=product.pk)
    cost = _d(unit_cost if unit_cost is not None else product.cost_price)
    batch = create_batch(
        product,
        _d(quantity),
        cost,
        source_type=StockBatch.SOURCE_RETURN,
        source_id=reference_id or (return_item.id if return_item else None),
        note="Qaytarish",
        set_product_cost=False,
    )
    if return_item is not None:
        SaleReturnItemBatch.objects.create(
            return_item=return_item,
            batch=batch,
            quantity=_d(quantity),
            unit_cost=cost,
        )
    return batch


@transaction.atomic
def reverse_return_batches(sale_return) -> None:
    """Qaytarish o'chirilganda — yaratilgan partiyalardan miqdorni ayirish."""
    from apps.sales.models import SaleReturnItemBatch

    if sale_return.status != sale_return.STATUS_COMPLETED:
        return

    for item in sale_return.items.all():
        allocs = list(
            SaleReturnItemBatch.objects.select_related("batch").filter(return_item=item)
        )
        product = Product.objects.select_for_update().get(pk=item.product_id)
        if allocs:
            for alloc in allocs:
                batch = StockBatch.objects.select_for_update().get(pk=alloc.batch_id)
                take = _d(alloc.quantity)
                have = _d(batch.qty_remaining)
                if have >= take:
                    batch.qty_remaining = have - take
                    batch.save(update_fields=["qty_remaining", "updated_at"])
                    _log_movement(
                        tenant=product.tenant,
                        product=product,
                        batch=batch,
                        movement_type=StockMovement.TYPE_RETURN_CANCEL,
                        quantity=take,
                        unit_cost=alloc.unit_cost,
                        reference_type="return",
                        reference_id=sale_return.id,
                    )
                else:
                    if have > ZERO:
                        batch.qty_remaining = ZERO
                        batch.save(update_fields=["qty_remaining", "updated_at"])
                    need = take - have
                    if need > ZERO:
                        consume_fifo(
                            product,
                            need,
                            reference_type="return_cancel",
                            reference_id=sale_return.id,
                            allow_negative=False,
                        )
        else:
            # Eski qaytarish — FIFO dan ayirish
            consume_fifo(
                product,
                _d(item.quantity),
                reference_type="return_cancel",
                reference_id=sale_return.id,
                allow_negative=False,
            )
        sync_product_quantity(product)


@transaction.atomic
def set_stock_absolute(
    product: Product,
    target_qty: Decimal,
    *,
    unit_cost: Decimal | None = None,
    audit_item=None,
) -> Decimal:
    """Reviziya: qoldiqni aniq qiymatga keltirish (partiyalar orqali)."""
    product = Product.objects.select_for_update().get(pk=product.pk)
    target = _d(target_qty)
    if target < ZERO:
        raise ValidationError({"quantity_after": "Qoldiq manfiy bo'lishi mumkin emas."})

    current = batch_remaining_sum(product)
    cost = _d(unit_cost if unit_cost is not None else product.cost_price)
    delta = target - current

    if delta > ZERO:
        create_batch(
            product,
            delta,
            cost,
            source_type=StockBatch.SOURCE_AUDIT,
            source_id=audit_item.id if audit_item else None,
            note="Reviziya (+)",
            set_product_cost=False,
        )
    elif delta < ZERO:
        consume_fifo(
            product,
            -delta,
            reference_type="audit",
            reference_id=audit_item.id if audit_item else None,
            allow_negative=False,
        )
    else:
        sync_product_quantity(product)

    return sync_product_quantity(product)


def stock_snapshot(products: Iterable[Product]) -> list[dict]:
    out = []
    for p in products:
        out.append(
            {
                "product_id": str(p.id),
                "name": p.name,
                "stock": str(p.quantity),
                "last_cost": str(p.cost_price),
            }
        )
    return out
