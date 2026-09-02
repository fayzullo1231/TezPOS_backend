"""
Barcha mahsulotlarni CSV ga eksport (reviziya uchun).

CSV format:
  nomi,barcode,hozirgi_qoldiq,yangi_qoldiq

Yangi_qoldiq ustunini do'kon sanab to'ldiradi, keyin:
  python manage.py set_product_stock --csv /root/qoldiq.csv

Ishlatish:
  python manage.py export_stock_csv --tenant kuloloptom -o /tmp/qoldiq.csv
"""

from __future__ import annotations

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Tenant
from apps.catalog.models import Product


class Command(BaseCommand):
    help = "Mahsulot qoldiqlarini reviziya CSV ga eksport"

    def add_arguments(self, parser):
        parser.add_argument("-o", "--output", type=str, required=True, help="Chiqish CSV fayli")
        parser.add_argument("--tenant", type=str, default="kuloloptom")
        parser.add_argument(
            "--only-nonzero",
            action="store_true",
            help="Faqat qoldiq != 0 mahsulotlar",
        )

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(server_name__iexact=options["tenant"].strip()).first()
        if not tenant:
            raise CommandError(f"Tenant topilmadi: {options['tenant']}")

        out = Path(options["output"]).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)

        qs = Product.objects.filter(is_active=True, tenant=tenant).order_by("name")
        if options["only_nonzero"]:
            qs = qs.exclude(quantity=0)

        count = 0
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["nomi", "barcode", "hozirgi_qoldiq", "yangi_qoldiq"])
            for p in qs.iterator(chunk_size=500):
                w.writerow([p.name, p.barcode or "", p.quantity, ""])
                count += 1

        self.stdout.write(self.style.SUCCESS(f"Yozildi: {count} ta -> {out}"))
        self.stdout.write("yangi_qoldiq ustunini to'ldiring, keyin:")
        self.stdout.write(f"  python manage.py set_product_stock --csv {out}")
