"""
Mahsulot qoldig'ini ombor harakatlari (StockMovement) jurnalidan qayta hisoblash.

Noto'g'ri skriptlar product.quantity ni to'g'ridan o'zgartirgan bo'lsa, jurnal aniqroq
bo'lishi mumkin. 100% kafolat uchun oxirida reviziya (fizik sanash) tavsiya etiladi.

Ishlatish:
  python manage.py recalc_stock_from_ledger --dry-run
  python manage.py recalc_stock_from_ledger

  # 14:40 gacha jurnal + keyingi harakatlar (tekshirish):
  python manage.py recalc_stock_from_ledger --anchor "2026-09-02 14:40" --dry-run
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.models import Product, StockMovement, StockReceipt, StockReceiptItem
from apps.sales.models import Sale, SaleItem, SaleReturn, SaleReturnItem

ZERO = Decimal("0")
OUT_TYPES = {
    StockMovement.TYPE_SALE,
    StockMovement.TYPE_RETURN_CANCEL,
}
IN_TYPES = {
    StockMovement.TYPE_OPENING,
    StockMovement.TYPE_RECEIPT,
    StockMovement.TYPE_RETURN,
    StockMovement.TYPE_SALE_CANCEL,
    StockMovement.TYPE_AUDIT,
    StockMovement.TYPE_ADJUSTMENT,
}


def _movement_delta(movement_type: str, qty: Decimal) -> Decimal:
    if movement_type in OUT_TYPES:
        return -qty
    if movement_type in IN_TYPES:
        return qty
    return ZERO


class Command(BaseCommand):
    help = "StockMovement jurnalidan qoldiqni qayta hisoblash"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--anchor",
            type=str,
            default="",
            help="Ma'lum vaqt (YYYY-MM-DD HH:MM) — shu paytgacha/ keyin tekshirish",
        )
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        dry = options["dry_run"]
        limit = options["limit"]
        anchor = self._parse_anchor(options["anchor"]) if options["anchor"] else None

        if anchor:
            self.stdout.write(f"Anchor: {anchor} (jurnal bo'yicha baseline)")

        updates: list[tuple[Product, Decimal, Decimal, str]] = []

        for product in Product.objects.filter(is_active=True).iterator(chunk_size=200):
            target, note = self._target_qty(product, anchor)
            if product.quantity == target:
                continue
            updates.append((product, product.quantity, target, note))

        updates.sort(key=lambda x: abs(x[2] - x[1]), reverse=True)
        if limit > 0:
            updates = updates[:limit]

        self.stdout.write(f"O'zgaradi: {len(updates)} ta" + (" (dry-run)" if dry else ""))

        changed = 0
        with transaction.atomic():
            for product, old, new, note in updates:
                self.stdout.write(
                    f"{'[dry] ' if dry else ''}{product.name[:50]}: {old} -> {new} ({note})"
                )
                if not dry:
                    product.quantity = new
                    product.save(update_fields=["quantity", "updated_at"])
                changed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Tayyor: {changed} ta yangilandi"
                + (" (dry-run)" if dry else "")
            )
        )
        if not dry and changed:
            self.stdout.write("POS: Sinxron tugmasini bosing.")
        self.stdout.write(
            "\n100% aniq qoldiq uchun: POS da Inventar → Reviziya (fizik sanash)."
        )

    def _parse_anchor(self, raw: str):
        raw = raw.strip()
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                tz = timezone.get_current_timezone()
                return timezone.make_aware(dt, tz) if timezone.is_naive(dt) else dt
            except ValueError:
                continue
        raise CommandError("Anchor format: YYYY-MM-DD HH:MM")

    def _ledger_net(self, product_id, until=None, since=None) -> Decimal:
        qs = StockMovement.objects.filter(product_id=product_id)
        if until is not None:
            qs = qs.filter(created_at__lte=until)
        if since is not None:
            qs = qs.filter(created_at__gt=since)
        net = ZERO
        for row in qs.values("movement_type", "quantity"):
            net += _movement_delta(row["movement_type"], Decimal(str(row["quantity"] or 0)))
        return net

    def _sales_net(self, product_id, since=None, until=None) -> Decimal:
        qs = SaleItem.objects.filter(
            product_id=product_id,
            sale__status=Sale.STATUS_COMPLETED,
        )
        if since:
            qs = qs.filter(
                sale__completed_at__gte=since,
            ) | qs.filter(sale__completed_at__isnull=True, sale__created_at__gte=since)
        if until:
            qs = qs.filter(
                sale__completed_at__lte=until,
            ) | qs.filter(sale__completed_at__isnull=True, sale__created_at__lte=until)
        sold = qs.aggregate(t=Sum("quantity"))["t"] or ZERO
        rqs = SaleReturnItem.objects.filter(
            product_id=product_id,
            sale_return__status=SaleReturn.STATUS_COMPLETED,
        )
        if since:
            rqs = rqs.filter(sale_return__completed_at__gte=since)
        if until:
            rqs = rqs.filter(sale_return__completed_at__lte=until)
        returned = rqs.aggregate(t=Sum("quantity"))["t"] or ZERO
        recv_qs = StockReceiptItem.objects.filter(
            product_id=product_id,
            receipt__status=StockReceipt.STATUS_COMPLETED,
        )
        if since:
            recv_qs = recv_qs.filter(receipt__completed_at__gte=since)
        if until:
            recv_qs = recv_qs.filter(receipt__completed_at__lte=until)
        received = recv_qs.aggregate(t=Sum("quantity"))["t"] or ZERO
        return received + returned - sold

    def _target_qty(self, product: Product, anchor):
        full_ledger = self._ledger_net(product.id)
        if not anchor:
            return full_ledger, "jurnal"

        before = self._ledger_net(product.id, until=anchor)
        after = self._ledger_net(product.id, since=anchor)
        # Tekshirish: anchor dan keyin sotuv/kirim
        flow_after = self._sales_net(product.id, since=anchor)
        target = before + after
        note = f"anchor {anchor:%H:%M} jurnal"
        if after != flow_after and abs(after - flow_after) > Decimal("0.001"):
            note += f" (sotuv/kirim farq {flow_after})"
        return target, note
