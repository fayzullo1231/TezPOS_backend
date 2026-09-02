"""
Mahsulot qoldig'i ma'lum vaqtda va keyin (sotuv/kirim bilan).

Ishlatish:
  python manage.py product_stock_at --name "hochland chiz" --at "2026-09-02 14:40"
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q, Sum
from django.utils import timezone

from apps.catalog.models import Product, StockAuditItem, StockMovement, StockReceipt, StockReceiptItem
from apps.sales.models import Sale, SaleItem, SaleReturn, SaleReturnItem

ZERO = Decimal("0")
OUT = {StockMovement.TYPE_SALE, StockMovement.TYPE_RETURN_CANCEL}
IN = {
    StockMovement.TYPE_OPENING,
    StockMovement.TYPE_RECEIPT,
    StockMovement.TYPE_RETURN,
    StockMovement.TYPE_SALE_CANCEL,
    StockMovement.TYPE_AUDIT,
    StockMovement.TYPE_ADJUSTMENT,
}


class Command(BaseCommand):
    help = "Mahsulot qoldig'i anchor vaqtda va keyingi harakatlar"

    def add_arguments(self, parser):
        parser.add_argument("--name", type=str, required=True)
        parser.add_argument("--barcode", type=str, default="")
        parser.add_argument(
            "--at",
            type=str,
            default="2026-09-02 14:40",
            help="Vaqt (Asia/Tashkent)",
        )

    def handle(self, *args, **options):
        at = self._parse_at(options["at"])
        products = self._find_products(options["name"], options["barcode"])
        if not products:
            raise CommandError(f"Mahsulot topilmadi: {options['name']}")

        for p in products:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(p.name))
            self.stdout.write(f"  ID: {p.id}  |  barcode: {p.barcode or '-'}")
            self.stdout.write(f"  Hozir (DB): {p.quantity}")

            at_qty = self._ledger_until(p.id, at)
            self.stdout.write(self.style.SUCCESS(f"  {at:%Y-%m-%d %H:%M} jurnal: {at_qty}"))

            sold = self._sum_since(SaleItem, Sale, "sale", p.id, at)
            ret = self._sum_since(SaleReturnItem, SaleReturn, "return", p.id, at)
            recv = self._sum_since(StockReceiptItem, StockReceipt, "receipt", p.id, at)
            self.stdout.write(f"  Keyin sotuv: -{sold}  |  kirim: +{recv}  |  qaytarish: +{ret}")
            calc_now = at_qty + recv + ret - sold
            self.stdout.write(f"  Hisob (14:40 + keyin): {calc_now}")

            audit = (
                StockAuditItem.objects.filter(
                    product_id=p.id,
                    audit__completed_at__lte=at,
                )
                .select_related("audit")
                .order_by("-audit__completed_at")
                .first()
            )
            if audit and audit.quantity_after is not None:
                self.stdout.write(
                    f"  Oxirgi reviziya ({audit.audit.completed_at}): "
                    f"{audit.quantity_before} -> {audit.quantity_after}"
                )

    def _parse_at(self, raw: str):
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(raw.strip(), fmt)
                tz = timezone.get_current_timezone()
                return timezone.make_aware(dt, tz) if timezone.is_naive(dt) else dt
            except ValueError:
                continue
        raise CommandError("Vaqt: YYYY-MM-DD HH:MM")

    def _find_products(self, name: str, barcode: str):
        if barcode:
            p = Product.objects.filter(barcode=barcode.strip(), is_active=True)
            return list(p[:5])
        q = name.strip()
        exact = list(Product.objects.filter(name__iexact=q, is_active=True)[:5])
        if exact:
            return exact
        return list(Product.objects.filter(name__icontains=q, is_active=True).order_by("name")[:10])

    def _ledger_until(self, product_id, until) -> Decimal:
        net = ZERO
        for row in StockMovement.objects.filter(
            product_id=product_id, created_at__lte=until
        ).values("movement_type", "quantity"):
            q = Decimal(str(row["quantity"] or 0))
            if row["movement_type"] in OUT:
                net -= q
            elif row["movement_type"] in IN:
                net += q
        return net

    def _parent_ids_since(self, model, status, at):
        return model.objects.filter(status=status).filter(
            Q(completed_at__gt=at) | Q(completed_at__isnull=True, created_at__gt=at)
        ).values_list("id", flat=True)

    def _sum_since(self, item_model, parent_model, kind, product_id, at) -> Decimal:
        if kind == "sale":
            ids = list(self._parent_ids_since(parent_model, parent_model.STATUS_COMPLETED, at))
            fk = "sale_id"
        elif kind == "return":
            ids = list(self._parent_ids_since(parent_model, parent_model.STATUS_COMPLETED, at))
            fk = "sale_return_id"
        else:
            ids = list(self._parent_ids_since(parent_model, StockReceipt.STATUS_COMPLETED, at))
            fk = "receipt_id"
        if not ids:
            return ZERO
        return (
            item_model.objects.filter(product_id=product_id, **{f"{fk}__in": ids}).aggregate(
                t=Sum("quantity")
            )["t"]
            or ZERO
        )
