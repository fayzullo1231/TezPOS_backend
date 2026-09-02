"""
Eski tezpos.db dan faqat mahsulot qoldiqlarini tiklash (to'liq almashtirmasdan).

Ishlatish:
  python manage.py restore_stock_from_sqlite /yo'l/eski/tezpos.db
  python manage.py restore_stock_from_sqlite /yo'l/eski/tezpos.db --dry-run
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Product


def _load_backup_rows(path: Path) -> list[dict]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    for table in ("catalog_product", "products_product"):
        try:
            cur.execute(
                f"SELECT id, barcode, quantity, name FROM {table} WHERE is_active = 1 OR is_active IS NULL"
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except sqlite3.OperationalError:
            continue
    conn.close()
    raise CommandError("Zaxira bazada catalog_product jadvali topilmadi")


class Command(BaseCommand):
    help = "Eski SQLite bazadan mahsulot qoldiqlarini tiklash"

    def add_arguments(self, parser):
        parser.add_argument("backup_db", type=str, help="Eski tezpos.db fayli")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Faqat ko'rsatish, yozmaslik",
        )

    def handle(self, *args, **options):
        path = Path(options["backup_db"]).expanduser().resolve()
        if not path.is_file():
            raise CommandError(f"Fayl topilmadi: {path}")

        backup_rows = _load_backup_rows(path)
        if not backup_rows:
            raise CommandError("Zaxira bazada mahsulot yo'q")

        by_id = {str(r["id"]): r for r in backup_rows if r.get("id")}
        by_barcode = {}
        for r in backup_rows:
            code = (r.get("barcode") or "").strip()
            if code:
                by_barcode[code] = r

        updated = 0
        skipped = 0
        dry = options["dry_run"]

        with transaction.atomic():
            for product in Product.objects.filter(is_active=True):
                src = by_id.get(str(product.id))
                if not src:
                    code = (product.barcode or "").strip()
                    if code:
                        src = by_barcode.get(code)

                if not src:
                    skipped += 1
                    continue

                old_qty = product.quantity
                new_qty = Decimal(str(src.get("quantity") or 0))
                if old_qty == new_qty:
                    skipped += 1
                    continue

                self.stdout.write(
                    f"{'[dry] ' if dry else ''}{product.name[:50]}: {old_qty} -> {new_qty}"
                )
                if not dry:
                    product.quantity = new_qty
                    product.save(update_fields=["quantity", "updated_at"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Tayyor: {updated} ta yangilandi, {skipped} ta o'zgarmadi"
                + (" (dry-run)" if dry else "")
            )
        )
