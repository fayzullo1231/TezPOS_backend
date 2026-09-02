"""
Ikki (yoki ko'p) manbani solishtirib, eng ko'p qoldiqlisidan tiklash.

Manbalar: joriy LIVE + /root/tezpos_*.db zaxiralar
Strategiya:
  best-file  — tannarx jami eng yuqori fayldan (butunlay)
  max-qty    — har mahsulotda max(joriy, zaxira)  [tavsiya]

Ishlatish:
  python manage.py restore_best_stock --tenant kuloloptom --dry-run
  python manage.py restore_best_stock --tenant kuloloptom
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from apps.accounts.models import Tenant
from apps.catalog.fifo import set_stock_absolute
from apps.catalog.management.commands.restore_stock_from_sqlite import load_backup_maps
from apps.catalog.models import Product

ZERO = Decimal("0")


def _fmt(v: Decimal) -> str:
    return f"{int(v):,}".replace(",", " ") + " so'm"


def _live_stats(tenant) -> tuple[Decimal, Decimal, dict]:
    """Returns (tannarx, jami_qty, {product_id: qty})."""
    qs = Product.objects.filter(is_active=True, tenant=tenant)
    agg = qs.aggregate(
        qty=Sum("quantity"),
        cost=Sum(
            ExpressionWrapper(
                F("quantity") * F("cost_price"),
                output_field=DecimalField(max_digits=24, decimal_places=2),
            )
        ),
    )
    qty_map = {str(p.id): p.quantity or ZERO for p in qs.only("id", "quantity")}
    return Decimal(str(agg["cost"] or 0)), Decimal(str(agg["qty"] or 0)), qty_map


def _backup_stats(tenant, path: Path, products) -> tuple[Decimal, Decimal, dict]:
    by_id, by_barcode = load_backup_maps(path)
    cost = ZERO
    qty_total = ZERO
    qty_map: dict[str, Decimal] = {}
    for p in products:
        q = by_id.get(str(p.id))
        if q is None:
            code = (p.barcode or "").strip()
            if code:
                q = by_barcode.get(code)
        if q is None:
            continue
        qty_map[str(p.id)] = q
        cost_p = Decimal(str(p.cost_price or 0))
        cost += q * cost_p
        qty_total += q
    return cost, qty_total, qty_map


def _find_backup_files() -> list[Path]:
    roots = [Path("/root"), Path("/opt/tezpos-backend/data")]
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.glob("tezpos*.db")):
            if p.name.endswith("-shm") or p.name.endswith("-wal"):
                continue
            if p.is_file() and p.stat().st_size > 100_000:
                found.append(p.resolve())
    # unique
    seen = set()
    out = []
    for p in found:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


class Command(BaseCommand):
    help = "Manbalarni solishtirish va eng ko'p qoldiqlisidan tiklash"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=str, default="kuloloptom")
        parser.add_argument(
            "--strategy",
            choices=["best-file", "max-qty"],
            default="max-qty",
            help="best-file=eng yuqori fayl; max-qty=har mahsulotda max",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(server_name__iexact=options["tenant"].strip()).first()
        if not tenant:
            raise CommandError(f"Tenant topilmadi: {options['tenant']}")

        products = list(Product.objects.filter(is_active=True, tenant=tenant))
        live_cost, live_qty, live_map = _live_stats(tenant)

        sources: list[tuple[str, Path | None, Decimal, Decimal, dict]] = [
            ("LIVE (joriy)", None, live_cost, live_qty, live_map),
        ]

        for path in _find_backup_files():
            if path == Path("/opt/tezpos-backend/data/tezpos.db"):
                continue
            try:
                c, q, m = _backup_stats(tenant, path, products)
                sources.append((path.name, path, c, q, m))
            except CommandError:
                continue

        self.stdout.write(self.style.MIGRATE_HEADING(f"Solishtirish ({tenant.server_name})"))
        self.stdout.write("")
        for name, path, cost, qty, _ in sorted(sources, key=lambda x: x[2], reverse=True):
            mark = ""
            self.stdout.write(
                f"  {name:40} tannarx={_fmt(cost):>22}  qoldiq={qty}"
            )

        best = max(sources, key=lambda x: x[2])
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"Eng yuqori tannarx: {best[0]} ({_fmt(best[2])})")
        )

        strategy = options["strategy"]
        dry = options["dry_run"]

        if strategy == "best-file":
            if best[1] is None:
                self.stdout.write(self.style.WARNING("Joriy LIVE eng yuqori — o'zgartirish shart emas."))
                return
            self._apply_from_map(products, best[4], dry, f"best-file:{best[0]}")
            return

        # max-qty: live vs har bir backup, keyin max
        all_maps = [s[4] for s in sources if s[4]]
        merged: dict[str, Decimal] = {}
        for p in products:
            pid = str(p.id)
            vals = [live_map.get(pid, ZERO)]
            for m in all_maps:
                if pid in m:
                    vals.append(m[pid])
            merged[pid] = max(vals)

        self._apply_from_map(products, merged, dry, "max-qty")

    def _apply_from_map(self, products, qty_map: dict, dry: bool, label: str):
        updated = 0
        with transaction.atomic():
            for p in products:
                pid = str(p.id)
                if pid not in qty_map:
                    continue
                new_q = qty_map[pid]
                old_q = p.quantity or ZERO
                if new_q == old_q:
                    continue
                if updated < 50:
                    self.stdout.write(
                        f"{'[dry] ' if dry else ''}[{label}] {p.name[:45]}: {old_q} -> {new_q}"
                    )
                if not dry:
                    if new_q >= ZERO:
                        set_stock_absolute(p, new_q)
                    else:
                        p.quantity = new_q
                        p.save(update_fields=["quantity", "updated_at"])
                updated += 1
        if updated > 50:
            self.stdout.write(f"... va yana {updated - 50} ta")
        self.stdout.write(self.style.SUCCESS(f"Tayyor: {updated} ta yangilandi" + (" (dry-run)" if dry else "")))
        if not dry and updated:
            self.stdout.write("POS: Sinxron bosing.")
