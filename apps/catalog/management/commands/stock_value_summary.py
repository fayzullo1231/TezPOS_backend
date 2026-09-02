"""
Ombor tannarx jami (POS dagi "Tannarx jami" kartasi).

Ishlatish:
  python manage.py stock_value_summary --tenant kuloloptom
  python manage.py stock_value_summary --backup-db /root/tezpos_sep2.db
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from apps.accounts.models import Tenant
from apps.catalog.models import Product

ZERO = Decimal("0")


def _fmt_money(v: Decimal) -> str:
    return f"{int(v):,}".replace(",", " ") + " so'm"


def _load_backup_rows(path: Path) -> list[dict]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    for table in ("catalog_product", "products_product"):
        try:
            cur.execute(
                f"SELECT id, barcode, quantity, cost_price, name FROM {table} "
                "WHERE is_active = 1 OR is_active IS NULL"
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except sqlite3.OperationalError:
            continue
    conn.close()
    raise CommandError(f"Backup jadvali topilmadi: {path}")


class Command(BaseCommand):
    help = "Ombor tannarx jami va qoldiq statistikasi"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=str, default="kuloloptom")
        parser.add_argument("--backup-db", type=str, default="")

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(server_name__iexact=options["tenant"].strip()).first()
        if not tenant:
            raise CommandError(f"Tenant topilmadi: {options['tenant']}")

        self._print_current(tenant)

        backup = (options.get("backup_db") or "").strip()
        if backup:
            self.stdout.write("")
            self._print_backup(Path(backup), tenant)

    def _print_current(self, tenant: Tenant):
        qs = Product.objects.filter(is_active=True, tenant=tenant)
        count = qs.count()
        agg = qs.aggregate(
            qty=Sum("quantity"),
            cost_val=Sum(
                ExpressionWrapper(
                    F("quantity") * F("cost_price"),
                    output_field=DecimalField(max_digits=24, decimal_places=2),
                )
            ),
            sale_val=Sum(
                ExpressionWrapper(
                    F("quantity") * F("price"),
                    output_field=DecimalField(max_digits=24, decimal_places=2),
                )
            ),
        )
        qty = Decimal(str(agg["qty"] or 0))
        cost = Decimal(str(agg["cost_val"] or 0))
        sale = Decimal(str(agg["sale_val"] or 0))
        minus_n = qs.filter(quantity__lt=0).count()
        zero_n = qs.filter(quantity=0).count()

        self.stdout.write(self.style.MIGRATE_HEADING(f"HOZIR ({tenant.server_name})"))
        self.stdout.write(f"  Tovarlar:      {count}")
        self.stdout.write(f"  Jami qoldiq:   {qty}")
        self.stdout.write(self.style.WARNING(f"  Tannarx jami:  {_fmt_money(cost)}"))
        self.stdout.write(f"  Sotuv jami:    {_fmt_money(sale)}")
        self.stdout.write(f"  Minus qoldiq:  {minus_n} ta | Nol: {zero_n} ta")

    def _print_backup(self, path: Path, tenant: Tenant):
        if not path.is_file():
            raise CommandError(f"Backup topilmadi: {path}")

        rows = _load_backup_rows(path)
        by_id = {str(r["id"]): r for r in rows if r.get("id")}
        by_barcode = {}
        for r in rows:
            code = (r.get("barcode") or "").strip()
            if code:
                by_barcode[code] = r

        total_qty = ZERO
        total_cost = ZERO
        total_sale = ZERO
        matched = 0

        for product in Product.objects.filter(is_active=True, tenant=tenant):
            src = by_id.get(str(product.id))
            if not src:
                code = (product.barcode or "").strip()
                if code:
                    src = by_barcode.get(code)
            if not src:
                continue
            matched += 1
            qty = Decimal(str(src.get("quantity") or 0))
            cost_p = Decimal(str(src.get("cost_price") or product.cost_price or 0))
            sale_p = Decimal(str(product.price or 0))
            total_qty += qty
            total_cost += qty * cost_p
            total_sale += qty * sale_p

        self.stdout.write(self.style.MIGRATE_HEADING(f"BACKUP ({path.name})"))
        self.stdout.write(f"  Mos keldi:     {matched} ta mahsulot")
        self.stdout.write(f"  Jami qoldiq:   {total_qty}")
        self.stdout.write(self.style.SUCCESS(f"  Tannarx jami:  {_fmt_money(total_cost)}"))
        self.stdout.write(f"  Sotuv jami:    {_fmt_money(total_sale)}")
