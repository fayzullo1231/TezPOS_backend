"""
JSON (POS localStorage tezpos_products export) dan FAQAT narxlarni tiklash.
Qoldiq va boshqa tenantlarga tegmaydi.

  python manage.py restore_prices_from_json products_kuloloptom-2.json --tenant kuloloptom-2 --dry-run
  python manage.py restore_prices_from_json products_kuloloptom-2.json --tenant kuloloptom-2
"""

from __future__ import annotations

import json
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


class Command(BaseCommand):
    help = "JSON mahsulot ro'yxatidan faqat narxlarni tiklash (bitta tenant)"

    def add_arguments(self, parser):
        parser.add_argument("json_file", type=str)
        parser.add_argument("--tenant", type=str, required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--no-cost", action="store_true")
        parser.add_argument("--no-list-prices", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["json_file"]).expanduser().resolve()
        if not path.is_file():
            raise CommandError(f"Fayl topilmadi: {path}")

        tenant = Tenant.objects.filter(server_name__iexact=options["tenant"].strip()).first()
        if not tenant:
            raise CommandError(f"Tenant topilmadi: {options['tenant']}")

        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise CommandError("JSON massiv bo'lishi kerak")

        by_id: dict[str, dict] = {}
        by_barcode: dict[str, dict] = {}
        for row in raw:
            if not isinstance(row, dict):
                continue
            pid = str(row.get("id") or "").strip()
            if pid:
                by_id[pid] = row
            code = (row.get("barcode") or "").strip()
            if code:
                by_barcode[code] = row
            for c in row.get("barcodes") or []:
                c = str(c or "").strip()
                if c:
                    by_barcode[c] = row

        dry = options["dry_run"]
        do_cost = not options["no_cost"]
        do_lists = not options["no_list_prices"]
        live_pl_ids = set(
            str(x)
            for x in PriceList.objects.filter(tenant=tenant, is_active=True).values_list(
                "id", flat=True
            )
        )

        updated = skipped = list_updated = 0
        samples: list[str] = []

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
                bits: list[str] = []

                if product.price != new_price:
                    bits.append(f"price {product.price} -> {new_price}")
                    if not dry:
                        product.price = new_price
                    fields.append("price")

                if do_cost and product.cost_price != new_cost:
                    bits.append(f"cost {product.cost_price} -> {new_cost}")
                    if not dry:
                        product.cost_price = new_cost
                    fields.append("cost_price")

                if fields:
                    updated += 1
                    if len(samples) < 40:
                        samples.append(
                            f"{'[dry] ' if dry else ''}{product.name[:45]}: " + "; ".join(bits)
                        )
                    if not dry:
                        fields.append("updated_at")
                        product.save(update_fields=fields)

                if do_lists:
                    lp = src.get("list_prices") or {}
                    if isinstance(lp, dict):
                        for pl_id, val in lp.items():
                            pl_id = str(pl_id)
                            if pl_id not in live_pl_ids:
                                continue
                            new_lp = _dec(val)
                            existing = ProductPrice.objects.filter(
                                product=product, price_list_id=pl_id, tenant=tenant
                            ).first()
                            if existing and existing.price == new_lp:
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

        self.stdout.write(self.style.MIGRATE_HEADING(f"TENANT: {tenant.server_name}"))
        self.stdout.write(f"  JSON: {path} ({len(raw)} ta)")
        self.stdout.write(f"  Narx o'zgarishi: {updated}")
        self.stdout.write(f"  List-price: {list_updated}")
        self.stdout.write(f"  Skip: {skipped}")
        for s in samples:
            self.stdout.write(f"  {s}")
        if dry:
            self.stdout.write(self.style.WARNING("DRY-RUN — yozilmadi"))
        else:
            self.stdout.write(self.style.SUCCESS("TAYYOR. POS Sinxron (faqat kuloloptom-2)."))
