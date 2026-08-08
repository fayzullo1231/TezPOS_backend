"""Mavjud Product.quantity dan boshlang'ich partiya (tarixiy sotuvlarga tegmasdan)."""

from decimal import Decimal

from django.db import migrations
from django.utils import timezone


def backfill_batches(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    StockBatch = apps.get_model("catalog", "StockBatch")
    StockMovement = apps.get_model("catalog", "StockMovement")

    now = timezone.now()
    zero = Decimal("0")
    batch_no_by_tenant = {}

    for product in Product.objects.all().iterator(chunk_size=200):
        qty = product.quantity or zero
        # Manfiy qoldiq — 0 ga tuzatiladi (FIFO manfiyga yo'l qo'ymaydi)
        if qty < zero:
            Product.objects.filter(pk=product.pk).update(quantity=zero)
            qty = zero

        if qty <= zero:
            continue

        # Allaqachon partiya bor bo'lsa — o'tkazib yubor
        if StockBatch.objects.filter(product_id=product.pk).exists():
            continue

        tid = product.tenant_id
        if tid not in batch_no_by_tenant:
            last = (
                StockBatch.objects.filter(tenant_id=tid)
                .order_by("-batch_number")
                .values_list("batch_number", flat=True)
                .first()
            )
            batch_no_by_tenant[tid] = int(last or 0)
        batch_no_by_tenant[tid] += 1

        batch = StockBatch.objects.create(
            tenant_id=tid,
            product_id=product.pk,
            batch_number=batch_no_by_tenant[tid],
            qty_received=qty,
            qty_remaining=qty,
            unit_cost=product.cost_price or zero,
            received_at=getattr(product, "created_at", None) or now,
            source_type="opening",
            note="Migratsiya: mavjud qoldiq",
        )
        StockMovement.objects.create(
            tenant_id=tid,
            product_id=product.pk,
            batch_id=batch.id,
            movement_type="opening",
            quantity=qty,
            unit_cost=product.cost_price or zero,
            reference_type="opening",
            note="Migratsiya: mavjud qoldiq",
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0013_fifo_stock_batches"),
    ]

    operations = [
        migrations.RunPython(backfill_batches, noop_reverse),
    ]
