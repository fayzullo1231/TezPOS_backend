"""
Eski tezpos.db dan qoldiqlarni tiklash (partiyalar bilan).

Ishlatish:
  python manage.py restore_stock_from_sqlite /root/tezpos_sep2.db --tenant kuloloptom
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Tenant
from apps.catalog.fifo import set_stock_absolute
from apps.catalog.models import Product

ZERO = Decimal("0")


def load_backup_maps(path: Path) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = None
    for table in ("catalog_product", "products_product"):
        try:
            cur.execute(
                f"SELECT id, barcode, quantity FROM {table} "
                "WHERE is_active = 1 OR is_active IS NULL"
            )
            rows = [dict(r) for r in cur.fetchall()]
            break
        except sqlite3.OperationalError:
            continue
    conn.close()
    if not rows:
        raise CommandError(f"Zaxira jadvali topilmadi: {path}")

    by_id: dict[str, Decimal] = {}
    by_barcode: dict[str, Decimal] = {}
    for r in rows:
        qty = Decimal(str(r.get("quantity") or 0))
        if r.get("id"):
            by_id[str(r["id"])] = qty
        code = (r.get("barcode") or "").strip()
        if code:
            by_barcode[code] = qty
    return by_id, by_barcode


class Command(BaseCommand):
    help = "SQLite zaxiradan qoldiq tiklash (FIFO partiyalar bilan)"

    def add_arguments(self, parser):
        parser.add_argument("backup_db", type=str)
        parser.add_argument("--tenant", type=str, default="kuloloptom")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["backup_db"]).expanduser().resolve()
        if not path.is_file():
            raise CommandError(f"Fayl topilmadi: {path}")

        tenant = Tenant.objects.filter(server_name__iexact=options["tenant"].strip()).first()
        if not tenant:
            raise CommandError(f"Tenant topilmadi: {options['tenant']}")

        by_id, by_barcode = load_backup_maps(path)
        dry = options["dry_run"]
        updated = skipped = 0

        with transaction.atomic():
            for product in Product.objects.filter(is_active=True, tenant=tenant).iterator(
                chunk_size=200
            ):
                new_qty = by_id.get(str(product.id))
                if new_qty is None:
                    code = (product.barcode or "").strip()
                    if code:
                        new_qty = by_barcode.get(code)
                if new_qty is None:
                    skipped += 1
                    continue
                old = product.quantity
                if old == new_qty:
                    skipped += 1
                    continue
                self.stdout.write(
                    f"{'[dry] ' if dry else ''}{product.name[:50]}: {old} -> {new_qty}"
                )
                if not dry:
                    if new_qty >= ZERO:
                        set_stock_absolute(product, new_qty)
                    else:
                        product.quantity = new_qty
                        product.save(update_fields=["quantity", "updated_at"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Tayyor: {updated} yangilandi, {skipped} o'zgarmadi"
                + (" (dry-run)" if dry else "")
            )
        )
        if not dry and updated:
            self.stdout.write("POS: Sinxron bosing.")
