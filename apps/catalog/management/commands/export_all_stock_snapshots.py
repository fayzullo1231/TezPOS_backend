"""
Serverdagi BARCHA zaxira va hozirgi qoldiqlarni bitta CSV ga eksport.

Har ustun — bitta vaqt/zaxira. Siz Excelda qaysi qoldiq to'g'ri tanlaysiz,
'tanlangan' ustuniga yozasiz, keyin set_product_stock bilan yuklaysiz.

Ishlatish:
  python manage.py export_all_stock_snapshots -o /tmp/barcha_qoldiq.csv
  python manage.py set_product_stock --csv /tmp/barcha_qoldiq.csv
"""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from apps.accounts.models import Tenant
from apps.catalog.management.commands.restore_best_stock import _find_backup_files
from apps.catalog.management.commands.restore_stock_from_sqlite import load_backup_maps
from apps.catalog.models import Product

ZERO = Decimal("0")


def _qty_for_product(product, by_id: dict, by_barcode: dict) -> Decimal | None:
    q = by_id.get(str(product.id))
    if q is None:
        code = (product.barcode or "").strip()
        if code:
            q = by_barcode.get(code)
    return q


def _snapshot_columns(path: Path) -> tuple[str, str]:
    """(ustun_nomi, tavsif)."""
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    ts = mtime.strftime("%Y-%m-%d %H:%M")
    label = path.name.replace(".", "_")[:48]
    return label, f"{path} @ {ts}"


def _tannarx_for_map(products, qty_map: dict[str, Decimal]) -> int:
    total = ZERO
    for p in products:
        pid = str(p.id)
        if pid not in qty_map:
            continue
        total += qty_map[pid] * Decimal(str(p.cost_price or 0))
    return int(total)


class Command(BaseCommand):
    help = "Barcha zaxira va hozirgi qoldiqlarni solishtirish CSV si"

    def add_arguments(self, parser):
        parser.add_argument("-o", "--output", type=str, default="/tmp/barcha_qoldiq.csv")
        parser.add_argument("--tenant", type=str, default="kuloloptom")
        parser.add_argument(
            "--summary",
            type=str,
            default="",
            help="Manbalar jadvali CSV (ixtiyoriy, masalan /tmp/qoldiq_manbalar.csv)",
        )

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(server_name__iexact=options["tenant"].strip()).first()
        if not tenant:
            raise CommandError(f"Tenant topilmadi: {options['tenant']}")

        products = list(Product.objects.filter(is_active=True, tenant=tenant).order_by("name"))
        out = Path(options["output"]).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)

        snapshots: list[tuple[str, str, dict[str, Decimal]]] = []

        live_map = {str(p.id): p.quantity or ZERO for p in products}
        snapshots.append(("hozir_LIVE", "Joriy server bazasi", live_map))

        seen_paths: set[Path] = set()
        for path in _find_backup_files():
            if path in seen_paths:
                continue
            seen_paths.add(path)
            if path.resolve() == Path("/opt/tezpos-backend/data/tezpos.db").resolve():
                continue
            try:
                by_id, by_barcode = load_backup_maps(path)
            except CommandError:
                continue
            col, desc = _snapshot_columns(path)
            qmap: dict[str, Decimal] = {}
            for p in products:
                q = _qty_for_product(p, by_id, by_barcode)
                if q is not None:
                    qmap[str(p.id)] = q
            snapshots.append((col, desc, qmap))

        # Sort zaxiralar by tannarx desc (hozir birinchi)
        live = snapshots[0]
        rest = snapshots[1:]
        rest.sort(key=lambda s: _tannarx_for_map(products, s[2]), reverse=True)
        snapshots = [live] + rest

        col_names = ["nomi", "barcode", "product_id", "tanlangan"] + [s[0] for s in snapshots]

        with out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(col_names)
            for p in products:
                pid = str(p.id)
                row = [p.name, p.barcode or "", pid, ""]
                for _, _, qmap in snapshots:
                    if pid in qmap:
                        row.append(qmap[pid])
                    else:
                        row.append("")
                w.writerow(row)

        self.stdout.write(self.style.SUCCESS(f"Mahsulotlar: {len(products)} ta -> {out}"))
        self.stdout.write("")
        self.stdout.write("Manbalar (tannarx jami):")
        for col, desc, qmap in snapshots:
            tv = _tannarx_for_map(products, qmap)
            self.stdout.write(f"  {col:40} {_fmt_int(tv)} so'm  |  {desc}")

        summary_path = (options.get("summary") or "").strip()
        if summary_path:
            sp = Path(summary_path).expanduser()
            with sp.open("w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["ustun", "tavsif", "tannarx_jami", "fayl"])
                for col, desc, qmap in snapshots:
                    w.writerow([col, desc, _tannarx_for_map(products, qmap), desc.split(" @ ")[0] if " @ " in desc else desc])
            self.stdout.write("")
            self.stdout.write(f"Manbalar jadvali: {sp}")

        self.stdout.write("")
        self.stdout.write("Keyingi qadam:")
        self.stdout.write("  1) Excelda oching, to'g'ri qoldiqni 'tanlangan' ustuniga yozing")
        self.stdout.write(f"  2) python manage.py set_product_stock --csv {out}")


def _fmt_int(v: int) -> str:
    return f"{v:,}".replace(",", " ")

