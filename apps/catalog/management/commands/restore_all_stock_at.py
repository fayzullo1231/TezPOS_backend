"""
Barcha mahsulot qoldig'ini anchor vaqtga qaytarish.

DIQQAT: 14:40 da DB zaxirasi yo'q. Jurnal ko'p mahsulotda 0.
Eski reviziya (avgust) ishlatilmasin — noto'g'ri qiymat beradi.

Usullar:
  unwind  — hozir + sotuv(keyin) - kirim(keyin) + qaytarish(keyin)  [tavsiya]
  ledger  — faqat jurnal(anchor gacha); ko'pini 0 qiladi
  flow    — jurnal(anchor) + kirim - sotuv + qaytarish (hozirgi holat)
  best    — ledger yoki unwind (reviziya ISHLATILMAYDI)

100% aniq: export_stock_csv + set_product_stock --csv

Ishlatish:
  python manage.py restore_all_stock_at --tenant kuloloptom --method unwind --dry-run
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.models import Tenant
from apps.catalog.fifo import set_stock_absolute
from apps.catalog.models import Product, StockMovement, StockReceipt, StockReceiptItem
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


def _ledger_map_until(until, product_ids: set | None = None) -> dict:
    net: dict = defaultdict(lambda: ZERO)
    qs = StockMovement.objects.filter(created_at__lte=until)
    if product_ids:
        qs = qs.filter(product_id__in=product_ids)
    for row in qs.values("product_id", "movement_type", "quantity"):
        q = Decimal(str(row["quantity"] or 0))
        if row["movement_type"] in OUT:
            net[row["product_id"]] -= q
        elif row["movement_type"] in IN:
            net[row["product_id"]] += q
    return dict(net)


def _has_movement_before(product_id, until) -> bool:
    return StockMovement.objects.filter(product_id=product_id, created_at__lte=until).exists()


class Command(BaseCommand):
    help = "Barcha qoldiqni anchor vaqtga qaytarish (1510 ta mahsulot)"

    def add_arguments(self, parser):
        parser.add_argument("--at", type=str, default="2026-09-02 14:40")
        parser.add_argument("--tenant", type=str, default="kuloloptom")
        parser.add_argument(
            "--method",
            type=str,
            default="unwind",
            choices=["ledger", "unwind", "flow", "best"],
            help="unwind=14:40 ga qaytarish; flow=hozirgacha jurnal; best=ledger yoki unwind",
        )
        parser.add_argument(
            "--min-flow",
            type=Decimal,
            default=None,
            help="unwind: faqat anchor dan keyin harakat bo'lgan mahsulotlar (masalan 0.001)",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        at = self._parse_at(options["at"])
        method = options["method"]
        dry = options["dry_run"]
        limit = options["limit"]
        min_flow = options.get("min_flow")

        tenant = Tenant.objects.filter(server_name__iexact=options["tenant"].strip()).first()
        if not tenant:
            raise CommandError(f"Tenant topilmadi: {options['tenant']}")

        products = list(Product.objects.filter(is_active=True, tenant=tenant))
        pids = {p.id for p in products}
        total = len(products)

        self.stdout.write(
            f"Anchor: {at:%Y-%m-%d %H:%M} | tenant: {tenant.server_name} | method: {method}"
        )
        self.stdout.write(f"Jami mahsulot: {total}")

        ledger = _ledger_map_until(at, pids)
        sold = self._flow_map(SaleItem, Sale, "sale", at, pids)
        received = self._flow_map(StockReceiptItem, StockReceipt, "receipt", at, pids)
        returned = self._flow_map(SaleReturnItem, SaleReturn, "return", at, pids)

        stats: dict[str, int] = defaultdict(int)
        updates: list[tuple[Product, Decimal, Decimal, str]] = []

        for product in products:
            pid = product.id
            flow_qty = sold.get(pid, ZERO) + received.get(pid, ZERO) + returned.get(pid, ZERO)
            if min_flow is not None and method == "unwind" and flow_qty < min_flow:
                stats["skip"] += 1
                continue

            target, source = self._resolve(product, method, at, ledger, sold, received, returned)
            stats[source] += 1
            if product.quantity == target:
                stats["unchanged"] += 1
                continue
            updates.append((product, product.quantity, target, source))

        updates.sort(key=lambda x: abs(x[2] - x[1]), reverse=True)
        if limit > 0:
            updates = updates[:limit]

        self.stdout.write(
            f"Manba: jurnal={stats['ledger']} unwind={stats['unwind']} flow={stats['flow']} "
            f"skip={stats['skip']} | o'zgarmaydi={stats['unchanged']}"
        )
        self.stdout.write(f"Yangilanadi: {len(updates)} ta" + (" (dry-run)" if dry else ""))

        shown = 0
        with transaction.atomic():
            for product, old, new, src in updates:
                if shown < 40:
                    self.stdout.write(
                        f"{'[dry] ' if dry else ''}[{src}] {product.name[:48]}: {old} -> {new}"
                    )
                shown += 1
                if not dry:
                    self._apply(product, new)

        if shown > 40:
            self.stdout.write(f"... va yana {shown - 40} ta")

        self.stdout.write(self.style.SUCCESS(f"Tayyor: {len(updates)} ta yangilandi"))
        if not dry:
            self.stdout.write("POS: Sinxron bosing.")

    def _resolve(self, product, method, at, ledger, sold, received, returned):
        pid = product.id
        cur = product.quantity or ZERO
        unwind = cur + sold.get(pid, ZERO) - received.get(pid, ZERO) + returned.get(pid, ZERO)
        led = ledger.get(pid, ZERO)
        flow = led + received.get(pid, ZERO) + returned.get(pid, ZERO) - sold.get(pid, ZERO)

        if method == "ledger":
            return led, "ledger"
        if method == "unwind":
            return unwind, "unwind"
        if method == "flow":
            return flow, "flow"

        # best: anchor gacha jurnal bor bo'lsa ledger@anchor, aks holda unwind
        if _has_movement_before(pid, at):
            return led, "ledger"
        return unwind, "unwind"

    def _apply(self, product, qty: Decimal):
        if qty >= ZERO:
            set_stock_absolute(product, qty)
        else:
            product.quantity = qty
            product.save(update_fields=["quantity", "updated_at"])

    def _parent_ids_since(self, model, at):
        return model.objects.filter(
            Q(completed_at__gt=at) | Q(completed_at__isnull=True, created_at__gt=at)
        ).values_list("id", flat=True)

    def _flow_map(self, item_model, parent_model, kind, at, pids) -> dict:
        if kind == "sale":
            ids = list(self._parent_ids_since(Sale, at))
            fk = "sale_id"
            status_filter = {"sale__status": Sale.STATUS_COMPLETED}
        elif kind == "return":
            ids = list(self._parent_ids_since(SaleReturn, at))
            fk = "sale_return_id"
            status_filter = {"sale_return__status": SaleReturn.STATUS_COMPLETED}
        else:
            ids = list(self._parent_ids_since(StockReceipt, at))
            fk = "receipt_id"
            status_filter = {"receipt__status": StockReceipt.STATUS_COMPLETED}
        if not ids:
            return {}
        return {
            row["product_id"]: row["t"] or ZERO
            for row in item_model.objects.filter(
                product_id__in=pids, **{f"{fk}__in": ids}, **status_filter
            )
            .values("product_id")
            .annotate(t=Sum("quantity"))
        }

    def _parse_at(self, raw: str):
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(raw.strip(), fmt)
                tz = timezone.get_current_timezone()
                return timezone.make_aware(dt, tz) if timezone.is_naive(dt) else dt
            except ValueError:
                continue
        raise CommandError("Vaqt: YYYY-MM-DD HH:MM")
