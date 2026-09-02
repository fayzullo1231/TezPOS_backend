"""
Partiyalarni Product.quantity ga moslashtirish (skriptlar buzganidan keyin).

Ishlatish:
  python manage.py rebuild_stock_batches --tenant kuloloptom --dry-run
  python manage.py rebuild_stock_batches --tenant kuloloptom
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Tenant
from apps.catalog.fifo import set_stock_absolute
from apps.catalog.models import Product

ZERO = Decimal("0")


class Command(BaseCommand):
    help = "FIFO partiyalarni mahsulot qoldig'iga moslashtirish"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=str, default="kuloloptom")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(server_name__iexact=options["tenant"].strip()).first()
        if not tenant:
            raise CommandError(f"Tenant topilmadi: {options['tenant']}")

        dry = options["dry_run"]
        changed = 0
        with transaction.atomic():
            for product in Product.objects.filter(is_active=True, tenant=tenant).iterator(
                chunk_size=200
            ):
                qty = product.quantity or ZERO
                if qty >= ZERO:
                    if not dry:
                        set_stock_absolute(product, qty)
                    changed += 1
                # minus: partiya yo'q, faqat quantity
        self.stdout.write(
            self.style.SUCCESS(f"Tayyor: {changed} ta" + (" (dry-run)" if dry else ""))
        )
