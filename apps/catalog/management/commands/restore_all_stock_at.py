"""
02.09.2026 14:40 holatiga qoldiqni qaytarish.

Usullar:
  backup  — Contabo DB (12:43) + 12:43..14:40 sotuv/kirim  [ENG ANIQ]
  unwind  — hozir + sotuv(14:40 dan) - kirim + qaytarish
  ledger  — faqat jurnal(14:40 gacha)

Ishlatish:
  # Contabo backup bor bo'lsa (tavsiya):
  python manage.py restore_all_stock_at --method backup \\
    --backup-db /root/tezpos_sep2.db --backup-at "2026-09-02 12:43"

  # Backup yo'q bo'lsa:
  python manage.py restore_all_stock_at --method unwind --dry-run
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

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


def _load_backup_qty_maps(path: Path) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = None
    for table in ("catalog_product", "products_product"):
        try:
            cur.execute(
                f"SELECT id, barcode, quantity FROM {table} "
                "WHERE is_active = 1 OR is_active IS NULL"
            )
            rows = [dict(r) for r in cur.fetchall()]
            break
        except sqlite3.OperationalError:
            continue
    conn.close()
    if not rows:
        raise CommandError(f"Zaxira bazada mahsulot jadvali topilmadi: {path}")

    by_id: dict[str, Decimal] = {}
    by_barcode: dict[str, Decimal] = {}
    for r in rows:
        qty = Decimal(str(r.get("quantity") or 0))
        if r.get("id"):
            by_id[str(r["id"])] = qty
        code = (r.get("barcode") or "").strip()
        if code:
            by_barcode[code] = qty
    return by_id, by_barcode


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
            default="auto",
            choices=["auto", "backup", "unwind", "ledger", "flow", "best"],
            help="auto=backup bor bo'lsa backup, aks holda unwind",
        )
        parser.add_argument(
            "--backup-db",
            type=str,
            default="",
            help="Contabo backup tezpos.db (masalan /root/tezpos_sep2.db)",
        )
        parser.add_argument(
            "--backup-at",
            type=str,
            default="2026-09-02 12:43",
            help="Backup vaqti (Contabo Auto Backup boshlangan vaqt)",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        at = self._parse_at(options["at"])
        method = options["method"]
        dry = options["dry_run"]
        limit = options["limit"]
        backup_db = (options.get("backup_db") or "").strip()
        backup_at = self._parse_at(options["backup_at"]) if options.get("backup_at") else None

        if method == "auto":
            method = "backup" if backup_db and Path(backup_db).is_file() else "unwind"

        if method == "backup":
            if not backup_db:
                raise CommandError("--backup-db kerak (Contabo tezpos.db)")
            if not Path(backup_db).is_file():
                raise CommandError(f"Backup topilmadi: {backup_db}")
            if backup_at is None:
                raise CommandError("--backup-at kerak")

        tenant = Tenant.objects.filter(server_name__iexact=options["tenant"].strip()).first()
        if not tenant:
            raise CommandError(f"Tenant topilmadi: {options['tenant']}")

        products = list(Product.objects.filter(is_active=True, tenant=tenant))
        pids = {p.id for p in products}
        total = len(products)

        self.stdout.write(
            f"Anchor: {at:%Y-%m-%d %H:%M} | tenant: {tenant.server_name} | method: {method}"
        )
        if method == "backup":
            self.stdout.write(
                f"Backup: {backup_db} @ {backup_at:%Y-%m-%d %H:%M} -> anchor {at:%H:%M}"
            )
        self.stdout.write(f"Jami mahsulot: {total}")

        backup_by_id: dict[str, Decimal] = {}
        backup_by_barcode: dict[str, Decimal] = {}
        if method == "backup":
            backup_by_id, backup_by_barcode = _load_backup_qty_maps(Path(backup_db))

        ledger = _ledger_map_until(at, pids)
        sold_since = self._flow_map_since(SaleItem, Sale, "sale", at, tenant, pids)
        recv_since = self._flow_map_since(StockReceiptItem, StockReceipt, "receipt", at, tenant, pids)
        ret_since = self._flow_map_since(SaleReturnItem, SaleReturn, "return", at, tenant, pids)

        sold_window = recv_window = ret_window = {}
        if method == "backup" and backup_at:
            sold_window = self._flow_map_between(
                SaleItem, Sale, "sale", backup_at, at, tenant, pids
            )
            recv_window = self._flow_map_between(
                StockReceiptItem, StockReceipt, "receipt", backup_at, at, tenant, pids
            )
            ret_window = self._flow_map_between(
                SaleReturnItem, SaleReturn, "return", backup_at, at, tenant, pids
            )

        stats: dict[str, int] = defaultdict(int)
        updates: list[tuple[Product, Decimal, Decimal, str]] = []

        for product in products:
            target, source = self._resolve(
                product,
                method,
                at,
                ledger,
                sold_since,
                recv_since,
                ret_since,
                backup_by_id,
                backup_by_barcode,
                sold_window,
                recv_window,
                ret_window,
            )
            stats[source] += 1
            if product.quantity == target:
                stats["unchanged"] += 1
                continue
            updates.append((product, product.quantity, target, source))

        updates.sort(key=lambda x: abs(x[2] - x[1]), reverse=True)
        if limit > 0:
            updates = updates[:limit]

        self.stdout.write(
            f"Manba: backup={stats['backup']} unwind={stats['unwind']} "
            f"jurnal={stats['ledger']} flow={stats['flow']} "
            f"| o'zgarmaydi={stats['unchanged']}"
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

    def _resolve(
        self,
        product,
        method,
        at,
        ledger,
        sold_since,
        recv_since,
        ret_since,
        backup_by_id,
        backup_by_barcode,
        sold_window,
        recv_window,
        ret_window,
    ):
        pid = product.id
        cur = product.quantity or ZERO
        unwind = cur + sold_since.get(pid, ZERO) - recv_since.get(pid, ZERO) + ret_since.get(pid, ZERO)
        led = ledger.get(pid, ZERO)
        flow = led + recv_since.get(pid, ZERO) + ret_since.get(pid, ZERO) - sold_since.get(pid, ZERO)

        if method == "backup":
            base = backup_by_id.get(str(pid))
            if base is None:
                code = (product.barcode or "").strip()
                if code:
                    base = backup_by_barcode.get(code)
            if base is None:
                base = ZERO
            target = (
                base
                + recv_window.get(pid, ZERO)
                + ret_window.get(pid, ZERO)
                - sold_window.get(pid, ZERO)
            )
            return target, "backup"

        if method == "ledger":
            return led, "ledger"
        if method == "unwind":
            return unwind, "unwind"
        if method == "flow":
            return flow, "flow"

        if _has_movement_before(pid, at):
            return led, "ledger"
        return unwind, "unwind"

    def _parent_time_filter(self, since=None, until=None):
        q = Q()
        if since is not None:
            q &= Q(completed_at__gt=since) | Q(completed_at__isnull=True, created_at__gt=since)
        if until is not None:
            q &= Q(completed_at__lte=until) | Q(completed_at__isnull=True, created_at__lte=until)
        return q

    def _flow_map_since(self, item_model, parent_model, kind, since, tenant, pids) -> dict:
        if kind == "sale":
            parents = Sale.objects.filter(tenant=tenant, status=Sale.STATUS_COMPLETED).filter(
                self._parent_time_filter(since=since)
            )
            fk = "sale_id"
            status_filter = {"sale__status": Sale.STATUS_COMPLETED}
        elif kind == "return":
            parents = SaleReturn.objects.filter(tenant=tenant, status=SaleReturn.STATUS_COMPLETED).filter(
                self._parent_time_filter(since=since)
            )
            fk = "sale_return_id"
            status_filter = {"sale_return__status": SaleReturn.STATUS_COMPLETED}
        else:
            parents = StockReceipt.objects.filter(tenant=tenant, status=StockReceipt.STATUS_COMPLETED).filter(
                self._parent_time_filter(since=since)
            )
            fk = "receipt_id"
            status_filter = {"receipt__status": StockReceipt.STATUS_COMPLETED}
        ids = list(parents.values_list("id", flat=True))
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

    def _flow_map_between(self, item_model, parent_model, kind, since, until, tenant, pids) -> dict:
        if kind == "sale":
            parents = Sale.objects.filter(tenant=tenant, status=Sale.STATUS_COMPLETED).filter(
                self._parent_time_filter(since=since, until=until)
            )
            fk = "sale_id"
            status_filter = {"sale__status": Sale.STATUS_COMPLETED}
        elif kind == "return":
            parents = SaleReturn.objects.filter(tenant=tenant, status=SaleReturn.STATUS_COMPLETED).filter(
                self._parent_time_filter(since=since, until=until)
            )
            fk = "sale_return_id"
            status_filter = {"sale_return__status": SaleReturn.STATUS_COMPLETED}
        else:
            parents = StockReceipt.objects.filter(tenant=tenant, status=StockReceipt.STATUS_COMPLETED).filter(
                self._parent_time_filter(since=since, until=until)
            )
            fk = "receipt_id"
            status_filter = {"receipt__status": StockReceipt.STATUS_COMPLETED}
        ids = list(parents.values_list("id", flat=True))
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

    def _apply(self, product, qty: Decimal):
        if qty >= ZERO:
            set_stock_absolute(product, qty)
        else:
            product.quantity = qty
            product.save(update_fields=["quantity", "updated_at"])


    def _parse_at(self, raw: str):
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(raw.strip(), fmt)
                tz = timezone.get_current_timezone()
                return timezone.make_aware(dt, tz) if timezone.is_naive(dt) else dt
            except ValueError:
                continue
        raise CommandError("Vaqt: YYYY-MM-DD HH:MM")
