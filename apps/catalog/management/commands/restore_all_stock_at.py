"""
BARCHA mahsulot qoldig'ini ma'lum vaqtga qaytarish (faqat shu payt, keyingi sotuvlar hisobga olinmaydi).

Ishlatish:
  python manage.py restore_all_stock_at --at "2026-09-02 14:40" --tenant kuloloptom --dry-run
  python manage.py restore_all_stock_at --at "2026-09-02 14:40" --tenant kuloloptom
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.catalog.fifo import set_stock_absolute
from apps.catalog.models import Product, StockMovement

ZERO = Decimal("0")
OUT = {StockMovement.TYPE_SALE, StockMovement.TYPE_RETURN_CANCEL}
IN = {
    StockMovement.TYPE_OPENING,
    StockMovement.TYPE_RECEIPT,
    StockMovement.TYPE_RETURN,
    StockMovement.TYPE_SALE_CANCEL,
    StockMovement.TYPE_AUDIT,
    StockMovement.TYPE_ADJUSTMENT,
}


def ledger_map_until(until) -> dict:
    net: dict = defaultdict(lambda: ZERO)
    for row in StockMovement.objects.filter(created_at__lte=until).values(
        "product_id", "movement_type", "quantity"
    ):
        q = Decimal(str(row["quantity"] or 0))
        if row["movement_type"] in OUT:
            net[row["product_id"]] -= q
        elif row["movement_type"] in IN:
            net[row["product_id"]] += q
    return dict(net)


class Command(BaseCommand):
    help = "Barcha qoldiqni anchor vaqtga qaytarish"

    def add_arguments(self, parser):
        parser.add_argument(
            "--at",
            type=str,
            default="2026-09-02 14:40",
            help="Qaytarish vaqti (Asia/Tashkent)",
        )
        parser.add_argument(
            "--tenant",
            type=str,
            default="kuloloptom",
            help="Server nomi (tenant)",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        at = self._parse_at(options["at"])
        tenant_name = (options["tenant"] or "").strip()
        dry = options["dry_run"]
        limit = options["limit"]

        tenant = None
        if tenant_name:
            tenant = Tenant.objects.filter(server_name__iexact=tenant_name).first()
            if not tenant:
                raise CommandError(f"Tenant topilmadi: {tenant_name}")

        self.stdout.write(
            f"Qaytarish: {at:%Y-%m-%d %H:%M} ({timezone.get_current_timezone()})"
        )
        if tenant:
            self.stdout.write(f"Tenant: {tenant.server_name}")

        baseline = ledger_map_until(at)
        qs = Product.objects.filter(is_active=True)
        if tenant:
            qs = qs.filter(tenant=tenant)

        updates: list[tuple[Product, Decimal, Decimal]] = []
        for product in qs.iterator(chunk_size=300):
            target = baseline.get(product.id, ZERO)
            if product.quantity != target:
                updates.append((product, product.quantity, target))

        updates.sort(key=lambda x: abs(x[2] - x[1]), reverse=True)
        if limit > 0:
            updates = updates[:limit]

        self.stdout.write(f"Yangilanadi: {len(updates)} ta" + (" (dry-run)" if dry else ""))

        changed = 0
        shown = 0
        with transaction.atomic():
            for product, old, new in updates:
                if shown < 30:
                    self.stdout.write(
                        f"{'[dry] ' if dry else ''}{product.name[:52]}: {old} -> {new}"
                    )
                shown += 1
                if not dry:
                    if new >= ZERO:
                        set_stock_absolute(product, new)
                    else:
                        product.quantity = new
                        product.save(update_fields=["quantity", "updated_at"])
                changed += 1

        if shown > 30:
            self.stdout.write(f"... va yana {shown - 30} ta")

        self.stdout.write(
            self.style.SUCCESS(f"Tayyor: {changed} ta" + (" (dry-run)" if dry else ""))
        )
        if not dry:
            self.stdout.write("POS: Sinxron tugmasini bosing (kuloloptom).")

    def _parse_at(self, raw: str):
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(raw.strip(), fmt)
                tz = timezone.get_current_timezone()
                return timezone.make_aware(dt, tz) if timezone.is_naive(dt) else dt
            except ValueError:
                continue
        raise CommandError("Vaqt: YYYY-MM-DD HH:MM")
