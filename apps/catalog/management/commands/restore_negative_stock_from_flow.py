"""
Kirim - sotuv + mijoz qaytarish bo'yicha minus qoldiqlarni tiklash.

Migratsiya 0014 manfiy qoldiqlarni 0 ga tushirgan. Bu buyruq tarixiy
harakatlardan qayta hisoblaydi: qoldiq = kirim + qaytarish - sotuv.

Ishlatish:
  python manage.py restore_negative_stock_from_flow --dry-run
  python manage.py restore_negative_stock_from_flow
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.catalog.models import Product, StockAuditItem, StockReceipt, StockReceiptItem
from apps.sales.models import Sale, SaleItem, SaleReturn, SaleReturnItem
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Kirim/sotuv tarixidan minus qoldiqlarni tiklash"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Faqat ko'rsatish, yozmaslik",
        )
        parser.add_argument(
            "--from-audits",
            action="store_true",
            help="Reviziyadagi quantity_after (manfiy) dan ham foydalanish",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Ko'rsatish limiti (0 = cheksiz)",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        use_audits = options["from_audits"]
        limit = options["limit"]

        sold_map = {
            row["product_id"]: row["t"] or Decimal("0")
            for row in SaleItem.objects.filter(sale__status=Sale.STATUS_COMPLETED)
            .values("product_id")
            .annotate(t=Sum("quantity"))
        }
        received_map = {
            row["product_id"]: row["t"] or Decimal("0")
            for row in StockReceiptItem.objects.filter(
                receipt__status=StockReceipt.STATUS_COMPLETED
            )
            .values("product_id")
            .annotate(t=Sum("quantity"))
        }
        returned_map = {
            row["product_id"]: row["t"] or Decimal("0")
            for row in SaleReturnItem.objects.filter(
                sale_return__status=SaleReturn.STATUS_COMPLETED
            )
            .values("product_id")
            .annotate(t=Sum("quantity"))
        }

        audit_map: dict = {}
        if use_audits:
            for row in (
                StockAuditItem.objects.filter(quantity_after__lt=0)
                .select_related("audit")
                .order_by("product_id", "-audit__completed_at", "-audit__created_at")
            ):
                pid = row.product_id
                if pid not in audit_map:
                    audit_map[pid] = row.quantity_after

        updates: list[tuple[Product, Decimal, Decimal, str]] = []
        for product in Product.objects.filter(is_active=True).only(
            "id", "name", "quantity", "updated_at"
        ):
            sold = sold_map.get(product.id, Decimal("0"))
            received = received_map.get(product.id, Decimal("0"))
            returned = returned_map.get(product.id, Decimal("0"))
            flow_net = received + returned - sold

            target = flow_net
            source = "kirim-sotuv"
            if use_audits and product.id in audit_map:
                audit_qty = Decimal(str(audit_map[product.id]))
                if audit_qty < target:
                    target = audit_qty
                    source = "reviziya"

            if target >= 0:
                continue
            if product.quantity == target:
                continue
            updates.append((product, product.quantity, target, source))

        updates.sort(key=lambda x: x[2])
        if limit > 0:
            updates = updates[:limit]

        self.stdout.write(
            f"Minus qoldiq tiklanadi: {len(updates)} ta mahsulot"
            + (" (dry-run)" if dry else "")
        )

        changed = 0
        with transaction.atomic():
            for product, old_qty, new_qty, source in updates:
                self.stdout.write(
                    f"{'[dry] ' if dry else ''}{product.name[:55]}: "
                    f"{old_qty} -> {new_qty} ({source})"
                )
                if not dry:
                    product.quantity = new_qty
                    product.save(update_fields=["quantity", "updated_at"])
                changed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Tayyor: {changed} ta mahsulot"
                + (" (dry-run — yozilmadi)" if dry else " yangilandi")
            )
        )
        if not dry and changed:
            self.stdout.write(
                "POS da Sinxron tugmasini bosing yoki dasturni qayta oching."
            )
