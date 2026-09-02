"""
Bitta yoki CSV orqali mahsulot qoldig'ini to'g'rilash (reviziya kabi).

CSV format (sarlavhasiz):
  mahsulot_nomi,yoki_shtrix,miqdor
  Tabiy qaymoq,,30
  ,4601234567890,15

Ishlatish:
  python manage.py set_product_stock --name "Tabiy qaymoq" --qty 30
  python manage.py set_product_stock --barcode 460... --qty 30
  python manage.py set_product_stock --csv /root/qoldiq.csv --dry-run
"""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.fifo import set_stock_absolute
from apps.catalog.models import Product

ZERO = Decimal("0")


class Command(BaseCommand):
    help = "Mahsulot qoldig'ini aniq qiymatga o'rnatish"

    def add_arguments(self, parser):
        parser.add_argument("--name", type=str, default="")
        parser.add_argument("--barcode", type=str, default="")
        parser.add_argument("--qty", type=str, default="")
        parser.add_argument("--csv", type=str, default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        rows: list[tuple[str, str, Decimal]] = []

        if options["csv"]:
            rows.extend(self._load_csv(options["csv"]))
        elif options["qty"]:
            rows.append(
                (
                    (options["name"] or "").strip(),
                    (options["barcode"] or "").strip(),
                    self._parse_qty(options["qty"]),
                )
            )
        else:
            raise CommandError("--name yoki --barcode va --qty, yoki --csv kerak")

        changed = 0
        with transaction.atomic():
            for name, barcode, qty in rows:
                product = self._find_product(name, barcode)
                if not product:
                    self.stdout.write(self.style.WARNING(f"Topilmadi: {name or barcode}"))
                    continue
                old = product.quantity
                if old == qty:
                    continue
                self.stdout.write(
                    f"{'[dry] ' if dry else ''}{product.name[:55]}: {old} -> {qty}"
                )
                if not dry:
                    if qty < ZERO:
                        product.quantity = qty
                        product.save(update_fields=["quantity", "updated_at"])
                    else:
                        set_stock_absolute(product, qty)
                changed += 1

        self.stdout.write(self.style.SUCCESS(f"Tayyor: {changed} ta" + (" (dry-run)" if dry else "")))
        if not dry and changed:
            self.stdout.write("POS: Sinxron tugmasini bosing.")

    def _parse_qty(self, raw: str) -> Decimal:
        try:
            return Decimal(str(raw).replace(",", ".").strip())
        except (InvalidOperation, ValueError) as exc:
            raise CommandError(f"Noto'g'ri miqdor: {raw}") from exc

    def _find_product(self, name: str, barcode: str) -> Product | None:
        if barcode:
            p = Product.objects.filter(barcode=barcode.strip(), is_active=True).first()
            if p:
                return p
        if name:
            exact = Product.objects.filter(name__iexact=name.strip(), is_active=True).first()
            if exact:
                return exact
            return Product.objects.filter(name__icontains=name.strip(), is_active=True).first()
        return None

    def _load_csv(self, path: str) -> list[tuple[str, str, Decimal]]:
        p = Path(path).expanduser()
        if not p.is_file():
            raise CommandError(f"CSV topilmadi: {p}")
        rows = []
        with p.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header: list[str] | None = None
            qty_idx: int | None = None
            name_idx = 0
            barcode_idx = 1

            for line in reader:
                if not line or all(not (c or "").strip() for c in line):
                    continue
                if len(line) < 2:
                    continue

                if header is None and line[0].lower() in (
                    "name",
                    "nomi",
                    "mahsulot",
                    "barcode",
                    "hozirgi_qoldiq",
                    "product_id",
                ):
                    header = [c.strip().lower() for c in line]
                    if "nomi" in header:
                        name_idx = header.index("nomi")
                    elif "name" in header:
                        name_idx = header.index("name")
                    if "barcode" in header:
                        barcode_idx = header.index("barcode")
                    for key in ("tanlangan", "yangi_qoldiq", "miqdor", "qty", "quantity"):
                        if key in header:
                            qty_idx = header.index(key)
                            break
                    continue

                if qty_idx is not None and len(line) > qty_idx:
                    qty_s = (line[qty_idx] or "").strip()
                    if not qty_s:
                        continue
                    name = line[name_idx] if len(line) > name_idx else ""
                    barcode = line[barcode_idx] if len(line) > barcode_idx else ""
                    rows.append((name.strip(), barcode.strip(), self._parse_qty(qty_s)))
                    continue

                # Eski formatlar
                if len(line) >= 4:
                    name, barcode, _extra, qty_s = line[0], line[1], line[2], line[3]
                    if not (qty_s or "").strip():
                        continue
                elif len(line) >= 3:
                    name, barcode, qty_s = line[0], line[1], line[2]
                else:
                    name, barcode, qty_s = line[0], "", line[1]
                rows.append((name.strip(), barcode.strip(), self._parse_qty(qty_s)))
        return rows
