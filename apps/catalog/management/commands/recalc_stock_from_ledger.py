"""
Qoldiqni anchor vaqtdan (masalan 14:40) hozirgacha qayta hisoblash.

Formula har mahsulot uchun:
  qoldiq = jurnal(anchor gacha) + kirim(keyin) + qaytarish(keyin) - sotuv(keyin)

Ishlatish:
  python manage.py recalc_stock_from_ledger --anchor "2026-09-02 14:40" --dry-run
  python manage.py recalc_stock_from_ledger --anchor "2026-09-02 14:40"
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.catalog.models import Product, StockMovement, StockReceipt, StockReceiptItem
from apps.sales.models import Sale, SaleItem, SaleReturn, SaleReturnItem

ZERO = Decimal("0")
OUT_TYPES = {StockMovement.TYPE_SALE, StockMovement.TYPE_RETURN_CANCEL}
IN_TYPES = {
    StockMovement.TYPE_OPENING,
    StockMovement.TYPE_RECEIPT,
    StockMovement.TYPE_RETURN,
    StockMovement.TYPE_SALE_CANCEL,
    StockMovement.TYPE_AUDIT,
    StockMovement.TYPE_ADJUSTMENT,
}


def _delta(movement_type: str, qty: Decimal) -> Decimal:
    if movement_type in OUT_TYPES:
        return -qty
    if movement_type in IN_TYPES:
        return qty
    return ZERO


class Command(BaseCommand):
    help = "Anchor vaqtdan hozirgacha qoldiqni qayta hisoblash"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--anchor",
            type=str,
            default="2026-09-02 14:40",
            help="To'g'ri qoldiq vaqti (Asia/Tashkent). Default: 2026-09-02 14:40",
        )
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument(
            "--only-changed",
            action="store_true",
            help="Faqat o'zgargan mahsulotlarni ko'rsatish",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        limit = options["limit"]
        only_changed = options["only_changed"]
        anchor = self._parse_anchor(options["anchor"])
        now = timezone.now()

        self.stdout.write(
            f"Anchor: {anchor:%Y-%m-%d %H:%M} ({timezone.get_current_timezone()})"
        )
        self.stdout.write(f"Hozir: {now:%Y-%m-%d %H:%M}")

        baseline = self._ledger_map(until=anchor)
        sold = self._sum_map(SaleItem, Sale.STATUS_COMPLETED, "sale", since=anchor)
        returned = self._sum_map(
            SaleReturnItem, SaleReturn.STATUS_COMPLETED, "return", since=anchor
        )
        received = self._sum_map(
            StockReceiptItem, StockReceipt.STATUS_COMPLETED, "receipt", since=anchor
        )

        updates: list[tuple[Product, Decimal, Decimal]] = []
        all_ids = set(baseline) | set(sold) | set(returned) | set(received)

        for product in Product.objects.filter(is_active=True).iterator(chunk_size=300):
            pid = product.id
            if pid not in all_ids and product.quantity == ZERO:
                continue
            base = baseline.get(pid, ZERO)
            flow = received.get(pid, ZERO) + returned.get(pid, ZERO) - sold.get(pid, ZERO)
            target = base + flow
            if product.quantity == target:
                continue
            updates.append((product, product.quantity, target))

        updates.sort(key=lambda x: abs(x[2] - x[1]), reverse=True)
        if limit > 0:
            updates = updates[:limit]

        self.stdout.write(f"Yangilanadi: {len(updates)} ta mahsulot" + (" (dry-run)" if dry else ""))

        shown = 0
        changed = 0
        with transaction.atomic():
            for product, old, new in updates:
                if only_changed and old == new:
                    continue
                if shown < 50 or not only_changed:
                    self.stdout.write(
                        f"{'[dry] ' if dry else ''}{product.name[:52]}: {old} -> {new}"
                    )
                shown += 1
                if not dry:
                    product.quantity = new
                    product.save(update_fields=["quantity", "updated_at"])
                changed += 1

        if only_changed and shown > 50:
            self.stdout.write(f"... va yana {shown - 50} ta")

        self.stdout.write(
            self.style.SUCCESS(
                f"Tayyor: {changed} ta yangilandi" + (" (dry-run)" if dry else "")
            )
        )
        if not dry:
            self.stdout.write("POS da Sinxron tugmasini bosing.")

    def _parse_anchor(self, raw: str):
        raw = (raw or "").strip()
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                tz = timezone.get_current_timezone()
                return timezone.make_aware(dt, tz) if timezone.is_naive(dt) else dt
            except ValueError:
                continue
        raise CommandError("Anchor: YYYY-MM-DD HH:MM")

    def _ledger_map(self, until=None, since=None) -> dict:
        qs = StockMovement.objects.all()
        if until is not None:
            qs = qs.filter(created_at__lte=until)
        if since is not None:
            qs = qs.filter(created_at__gt=since)
        net: dict = defaultdict(lambda: ZERO)
        for row in qs.values("product_id", "movement_type", "quantity"):
            net[row["product_id"]] += _delta(
                row["movement_type"], Decimal(str(row["quantity"] or 0))
            )
        return dict(net)

    def _sale_ids_since(self, since):
        return Sale.objects.filter(status=Sale.STATUS_COMPLETED).filter(
            Q(completed_at__gt=since)
            | Q(completed_at__isnull=True, created_at__gt=since)
        ).values_list("id", flat=True)

    def _return_ids_since(self, since):
        return SaleReturn.objects.filter(status=SaleReturn.STATUS_COMPLETED).filter(
            Q(completed_at__gt=since)
            | Q(completed_at__isnull=True, created_at__gt=since)
        ).values_list("id", flat=True)

    def _receipt_ids_since(self, since):
        return StockReceipt.objects.filter(status=StockReceipt.STATUS_COMPLETED).filter(
            Q(completed_at__gt=since)
            | Q(completed_at__isnull=True, created_at__gt=since)
        ).values_list("id", flat=True)

    def _sum_map(self, item_model, parent_status, kind: str, since) -> dict:
        if kind == "sale":
            parent_ids = list(self._sale_ids_since(since))
            fk = "sale_id"
        elif kind == "return":
            parent_ids = list(self._return_ids_since(since))
            fk = "sale_return_id"
        else:
            parent_ids = list(self._receipt_ids_since(since))
            fk = "receipt_id"

        if not parent_ids:
            return {}

        return {
            row["product_id"]: row["t"] or ZERO
            for row in item_model.objects.filter(**{f"{fk}__in": parent_ids})
            .values("product_id")
            .annotate(t=Sum("quantity"))
        }
