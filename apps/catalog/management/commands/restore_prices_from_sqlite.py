"""
Bitta tenant uchun FAQAT narxlarni SQLite zaxiradan tiklash.
Qoldiq (quantity), sotuvlar, boshqa tenantlarga TEKMAYDI.

Ishlatish:
  python manage.py restore_prices_from_sqlite /root/tezpos_prices.db \\
      --tenant kuloloptom-2 --dry-run
  python manage.py restore_prices_from_sqlite /root/tezpos_prices.db \\
      --tenant kuloloptom-2
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Tenant
from apps.catalog.models import PriceList, Product, ProductPrice

ZERO = Decimal("0")


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v if v is not None else 0))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def _load_product_prices(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.cursor()
    for table in ("catalog_product", "products_product"):
        try:
            cur.execute(
                f"SELECT id, barcode, name, price, cost_price, tenant_id FROM {table}"
            )
            return [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError:
            continue
    raise CommandError("catalog_product jadvali topilmadi")


def _load_list_prices(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT product_id, price_list_id, price, tenant_id "
            "FROM catalog_productprice"
        )
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        return []


def _tenant_ids_for_server(conn: sqlite3.Connection, server_name: str) -> set[str]:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, server_name FROM accounts_tenant WHERE lower(server_name)=lower(?)",
            (server_name,),
        )
        rows = cur.fetchall()
        return {str(r["id"]) for r in rows}
    except sqlite3.OperationalError:
        return set()


class Command(BaseCommand):
    help = "Bitta tenant uchun faqat narxlarni SQLite zaxiradan tiklash"

    def add_arguments(self, parser):
        parser.add_argument("backup_db", type=str)
        parser.add_argument(
            "--tenant",
            type=str,
            required=True,
            help="Faqat shu server_name (masalan kuloloptom-2)",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--include-cost",
            action="store_true",
            help="cost_price ham tiklansin (default: ha)",
            default=True,
        )
        parser.add_argument(
            "--no-cost",
            action="store_true",
            help="Faqat sotuv narxi (price), tannarxga tegma",
        )
        parser.add_argument(
            "--list-prices",
            action="store_true",
            default=True,
            help="Narxlar ro'yxati (optom va h.k.) ham tiklansin",
        )
        parser.add_argument("--no-list-prices", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["backup_db"]).expanduser().resolve()
        if not path.is_file():
            raise CommandError(f"Fayl topilmadi: {path}")

        server = options["tenant"].strip()
        tenant = Tenant.objects.filter(server_name__iexact=server).first()
        if not tenant:
            names = list(
                Tenant.objects.order_by("server_name").values_list("server_name", flat=True)[:50]
            )
            raise CommandError(
                f"Tenant topilmadi: {server}\nMavjud: {', '.join(names) or '(bo‘sh)'}"
            )

        dry = options["dry_run"]
        do_cost = not options.get("no_cost")
        do_lists = options.get("list_prices", True) and not options.get("no_list_prices")

        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        backup_tenant_ids = _tenant_ids_for_server(conn, server)
        if not backup_tenant_ids:
            # ID bo'yicha: live tenant id backupda ham shu bo'lishi mumkin
            backup_tenant_ids = {str(tenant.id)}
            self.stdout.write(
                self.style.WARNING(
                    f"Backupda '{server}' topilmadi — live tenant_id={tenant.id} bilan filtrlanadi"
                )
            )

        products = _load_product_prices(conn)
        list_rows = _load_list_prices(conn) if do_lists else []
        conn.close()

        by_id: dict[str, dict] = {}
        by_barcode: dict[str, dict] = {}
        for r in products:
            if str(r.get("tenant_id") or "") not in backup_tenant_ids:
                continue
            pid = str(r["id"])
            by_id[pid] = r
            code = (r.get("barcode") or "").strip()
            if code:
                by_barcode[code] = r

        list_by_product: dict[str, list[dict]] = {}
        for r in list_rows:
            if str(r.get("tenant_id") or "") not in backup_tenant_ids:
                continue
            list_by_product.setdefault(str(r["product_id"]), []).append(r)

        live_pl_ids = set(
            str(x)
            for x in PriceList.objects.filter(tenant=tenant, is_active=True).values_list(
                "id", flat=True
            )
        )

        updated = 0
        skipped = 0
        list_updated = 0
        changed_samples: list[str] = []

        with transaction.atomic():
            for product in Product.objects.filter(tenant=tenant).iterator(chunk_size=200):
                src = by_id.get(str(product.id))
                if not src:
                    code = (product.barcode or "").strip()
                    if code:
                        src = by_barcode.get(code)
                if not src:
                    skipped += 1
                    continue

                new_price = _dec(src.get("price"))
                new_cost = _dec(src.get("cost_price"))
                fields: list[str] = []
                line_bits: list[str] = []

                if product.price != new_price:
                    line_bits.append(f"price {product.price} -> {new_price}")
                    if not dry:
                        product.price = new_price
                    fields.append("price")

                if do_cost and product.cost_price != new_cost:
                    line_bits.append(f"cost {product.cost_price} -> {new_cost}")
                    if not dry:
                        product.cost_price = new_cost
                    fields.append("cost_price")

                if fields:
                    updated += 1
                    if len(changed_samples) < 30:
                        changed_samples.append(
                            f"{'[dry] ' if dry else ''}{product.name[:45]}: "
                            + "; ".join(line_bits)
                        )
                    if not dry:
                        fields.append("updated_at")
                        product.save(update_fields=fields)

                if do_lists:
                    for lr in list_by_product.get(str(product.id), []):
                        pl_id = str(lr["price_list_id"])
                        if pl_id not in live_pl_ids:
                            continue
                        new_lp = _dec(lr.get("price"))
                        existing = ProductPrice.objects.filter(
                            product=product, price_list_id=pl_id, tenant=tenant
                        ).first()
                        if existing and existing.price == new_lp:
                            continue
                        if existing is None and new_lp == ZERO:
                            continue
                        list_updated += 1
                        if not dry:
                            ProductPrice.objects.update_or_create(
                                product=product,
                                price_list_id=pl_id,
                                defaults={"tenant": tenant, "price": new_lp},
                            )

            if dry:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"TENANT: {tenant.server_name}"))
        self.stdout.write(f"  Backup:           {path}")
        self.stdout.write(f"  Mahsulot o'zgarishi: {updated}")
        self.stdout.write(f"  List-price yangilandi: {list_updated}")
        self.stdout.write(f"  Skip (topilmadi): {skipped}")
        for s in changed_samples:
            self.stdout.write(f"  {s}")
        if len(changed_samples) >= 30:
            self.stdout.write("  ...")
        if dry:
            self.stdout.write(self.style.WARNING("DRY-RUN — hech narsa yozilmadi"))
        else:
            self.stdout.write(self.style.SUCCESS("TAYYOR. POS da Sinxron bosing."))
            self.stdout.write("Boshqa tenantlarga tegilmadi.")
