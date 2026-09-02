"""
Partiya + so'nggi sotuvlar bo'yicha minus qoldiqni tiklash.

NOTO'G'RI (eski): butun tarix kirim-sotuv — minglab noto'g'ri minus beradi.
TO'G'RI: batch_qoldiq + partiyadan_sotilgan - davrdagi_sotuv

Ishlatish:
  # Avval noto'g'ri minusni tozalash + to'g'ri hisob (dry-run)
  python manage.py restore_negative_stock_from_flow --reset-from-batches --since 2026-09-01 --dry-run

  # Tasdiqlash
  python manage.py restore_negative_stock_from_flow --reset-from-batches --since 2026-09-01
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.catalog.fifo import batch_remaining_sum, sync_product_quantity
from apps.catalog.models import Product, StockBatch
from apps.sales.models import Sale, SaleItem, SaleItemBatch


class Command(BaseCommand):
    help = "Partiya va davr bo'yicha minus qoldiqni tiklash (butun tarix emas)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Faqat ko'rsatish, yozmaslik",
        )
        parser.add_argument(
            "--since",
            type=str,
            default="2026-09-01",
            help="Faqat shu sanadan keyingi sotuvlar (YYYY-MM-DD). Default: 2026-09-01",
        )
        parser.add_argument(
            "--reset-from-batches",
            action="store_true",
            help="Avval qoldiqni partiyalardan tiklash (noto'g'ri minusni tozalash)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Ko'rsatish limiti (0 = cheksiz)",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        limit = options["limit"]
        reset = options["reset_from_batches"]

        since = self._parse_since(options["since"])
        self.stdout.write(f"Davr: {since.date()} dan keyingi sotuvlar")

        if reset:
            self.stdout.write("==> Partiyalardan qoldiq tiklanmoqda...")
            reset_n = 0
            with transaction.atomic():
                for product in Product.objects.filter(is_active=True).iterator(chunk_size=300):
                    before = product.quantity
                    if dry:
                        new_qty = batch_remaining_sum(product)
                    else:
                        new_qty = sync_product_quantity(product)
                    if before != new_qty:
                        reset_n += 1
            self.stdout.write(f"Partiyaga moslashtirildi: {reset_n} ta mahsulot")

        sold_map = self._sum_since(
            SaleItem.objects.filter(sale__status=Sale.STATUS_COMPLETED),
            "quantity",
            since,
        )
        allocated_map = self._sum_allocated_since(since)

        batch_map = {
            row["product_id"]: row["t"] or Decimal("0")
            for row in StockBatch.objects.values("product_id").annotate(t=Sum("qty_remaining"))
        }

        updates: list[tuple[Product, Decimal, Decimal]] = []
        for product in Product.objects.filter(is_active=True).only(
            "id", "name", "quantity", "updated_at"
        ):
            batch_rem = batch_map.get(product.id, Decimal("0"))
            sold = sold_map.get(product.id, Decimal("0"))
            allocated = allocated_map.get(product.id, Decimal("0"))
            # batch + partiyadan ketgan - jami sotuv = haqiqiy qoldiq
            target = batch_rem + allocated - sold

            if target >= 0:
                continue
            if product.quantity == target:
                continue
            updates.append((product, product.quantity, target))

        updates.sort(key=lambda x: x[2])
        if limit > 0:
            updates = updates[:limit]

        self.stdout.write(
            f"Minus qoldiq: {len(updates)} ta mahsulot"
            + (" (dry-run)" if dry else "")
        )

        changed = 0
        with transaction.atomic():
            for product, old_qty, new_qty in updates:
                self.stdout.write(
                    f"{'[dry] ' if dry else ''}{product.name[:55]}: {old_qty} -> {new_qty}"
                )
                if not dry:
                    product.quantity = new_qty
                    product.save(update_fields=["quantity", "updated_at"])
                changed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Tayyor: {changed} ta"
                + (" (dry-run)" if dry else " yangilandi")
            )
        )

    def _parse_since(self, raw: str):
        try:
            dt = datetime.strptime(raw.strip(), "%Y-%m-%d")
        except ValueError as exc:
            raise CommandError("Sana formati: YYYY-MM-DD") from exc
        tz = timezone.get_current_timezone()
        return timezone.make_aware(dt, tz) if timezone.is_naive(dt) else dt

    def _sale_since_filter(self, since):
        return Sale.objects.filter(status=Sale.STATUS_COMPLETED).filter(
            Q(completed_at__gte=since)
            | Q(completed_at__isnull=True, created_at__gte=since)
        )

    def _sum_since(self, qs, field: str, since):
        sale_ids = self._sale_since_filter(since).values_list("id", flat=True)
        return {
            row["product_id"]: row["t"] or Decimal("0")
            for row in qs.filter(sale_id__in=sale_ids)
            .values("product_id")
            .annotate(t=Sum(field))
        }

    def _sum_allocated_since(self, since):
        sale_ids = self._sale_since_filter(since).values_list("id", flat=True)
        return {
            row["sale_item__product_id"]: row["t"] or Decimal("0")
            for row in SaleItemBatch.objects.filter(sale_item__sale_id__in=sale_ids)
            .values("sale_item__product_id")
            .annotate(t=Sum("quantity"))
        }
