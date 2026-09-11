"""ABC analiz — sotuv / foyda / dona bo'yicha Pareto (A≤80%, B≤95%, C).

Cost: SaleItemBatch.unit_cost (FIFO). Yo'q bo'lsa Product.cost_price.
Kanal: price_list_id + birlik narx vs sotuv/optom narx (POS ko'pincha price_list_id yubormaydi).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db.models import F, Q, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import PriceList, Product, ProductPrice
from apps.sales.models import Sale, SaleItem, SaleItemBatch

ZERO = Decimal("0")
Q2 = Decimal("0.01")
Q3 = Decimal("0.001")

ABC_THRESHOLDS = {"A": Decimal("80"), "B": Decimal("95")}


def _d(v, q=Q2) -> Decimal:
    if v is None:
        return ZERO
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v)).quantize(q)
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def _parse_date(raw: str | None):
    s = (raw or "").strip()[:10]
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _range_from_params(params) -> tuple:
    today = timezone.localdate()
    preset = (params.get("preset") or "").strip().lower()
    df = _parse_date(params.get("date_from") or params.get("from"))
    dt = _parse_date(params.get("date_to") or params.get("to"))

    if df and dt:
        if df > dt:
            df, dt = dt, df
        return df, dt, "custom"

    if preset in ("today", "bugun"):
        return today, today, "today"
    if preset in ("yesterday", "kecha"):
        y = today - timedelta(days=1)
        return y, y, "yesterday"
    if preset in ("7d", "7"):
        return today - timedelta(days=6), today, "7d"
    if preset in ("30d", "30"):
        return today - timedelta(days=29), today, "30d"
    if preset in ("month", "this_month", "joriy_oy"):
        return today.replace(day=1), today, "month"
    if preset in ("last_month", "otgan_oy"):
        first = today.replace(day=1)
        last_prev = first - timedelta(days=1)
        return last_prev.replace(day=1), last_prev, "last_month"
    if preset in ("3m", "90"):
        return today - timedelta(days=89), today, "3m"
    if preset in ("6m", "180"):
        return today - timedelta(days=179), today, "6m"
    if preset in ("1y", "365", "year"):
        return today - timedelta(days=364), today, "1y"

    return today - timedelta(days=29), today, "30d"


def _fmt_money(n: Decimal) -> str:
    v = float(n or 0)
    sign = "-" if v < 0 else ""
    return f"{sign}{abs(v):,.0f}".replace(",", " ")


def _margin(profit: Decimal, sales: Decimal) -> float | None:
    if sales == 0:
        return None
    return float((profit / sales * 100).quantize(Decimal("0.01")))


def _is_selling_list_name(name: str) -> bool:
    lower = (name or "").lower()
    return any(
        x in lower
        for x in (
            "sotuv",
            "sotish",
            "chakana",
            "retail",
            "selling",
            "продаж",
            "розниц",
        )
    )


def _is_optom_list_name(name: str) -> bool:
    lower = (name or "").lower()
    return any(x in lower for x in ("optom", "wholesale", "ulgurji", "опт"))


def _price_lists_meta(tenant) -> tuple[set[str], set[str]]:
    """(selling_ids, wholesale_ids)."""
    selling: set[str] = set()
    wholesale: set[str] = set()
    for pl in PriceList.objects.filter(tenant=tenant, is_active=True).only(
        "id", "name", "is_selling"
    ):
        sid = str(pl.id)
        if pl.is_selling or (_is_selling_list_name(pl.name) and not _is_optom_list_name(pl.name)):
            selling.add(sid)
        else:
            wholesale.add(sid)
    return selling, wholesale


def _wholesale_prices_by_product(tenant, wholesale_ids: set[str]) -> dict[str, list[Decimal]]:
    out: dict[str, list[Decimal]] = defaultdict(list)
    if not wholesale_ids:
        return out
    qs = ProductPrice.objects.filter(
        tenant=tenant, price_list_id__in=list(wholesale_ids), price__gt=0
    ).values_list("product_id", "price")
    for pid, price in qs:
        out[str(pid)].append(_d(price))
    return out


def _near(a: Decimal, b: Decimal) -> bool:
    if b <= 0 or a <= 0:
        return False
    tol = max(Decimal("1"), (b * Decimal("0.02")).quantize(Q2))
    return abs(a - b) <= tol


def classify_channel(
    *,
    unit_price,
    selling_price,
    wholesale_prices: list[Decimal],
    price_list_id: str | None,
    selling_ids: set[str],
    wholesale_ids: set[str],
) -> str:
    """retail | wholesale — price_list_id + birlik narx."""
    plid = (price_list_id or "").strip()
    up = _d(unit_price)
    sell = _d(selling_price)
    whs = [p for p in (wholesale_prices or []) if p > 0]

    if plid:
        if plid in wholesale_ids:
            return "wholesale"
        if plid in selling_ids:
            return "retail"
        # Noma'lum UUID — odatda optom/boshqa ro'yxat
        if plid not in selling_ids:
            # Agar aniq sotuv narxiga teng bo'lsa — sotuv
            if sell > 0 and _near(up, sell):
                return "retail"
            return "wholesale"

    for wp in whs:
        if _near(up, wp) and (sell <= 0 or up <= sell - Decimal("0.5")):
            return "wholesale"

    if sell > 0 and _near(up, sell):
        return "retail"

    if sell > 0 and up > 0 and up < sell - Decimal("0.5") and whs:
        return "wholesale"

    return "retail"


def build_abc_payload(
    tenant,
    *,
    date_from,
    date_to,
    metric: str = "sales",
    channel: str = "all",
    a_max: Decimal | None = None,
    b_max: Decimal | None = None,
) -> dict[str, Any]:
    a_max = a_max if a_max is not None else ABC_THRESHOLDS["A"]
    b_max = b_max if b_max is not None else ABC_THRESHOLDS["B"]
    metric = (metric or "sales").lower()
    if metric not in ("sales", "profit", "qty", "quantity"):
        metric = "sales"
    if metric == "quantity":
        metric = "qty"
    channel = (channel or "all").lower()
    if channel not in ("all", "retail", "wholesale", "optom", "sotuv"):
        channel = "all"
    if channel == "optom":
        channel = "wholesale"
    if channel == "sotuv":
        channel = "retail"

    selling_ids, wholesale_ids = _price_lists_meta(tenant)
    wh_by_product = _wholesale_prices_by_product(tenant, wholesale_ids)

    base_sale = Q(
        sale__tenant=tenant,
        sale__status=Sale.STATUS_COMPLETED,
        sale__completed_at__date__gte=date_from,
        sale__completed_at__date__lte=date_to,
    )

    sales_rows = (
        SaleItem.objects.filter(base_sale)
        .values(
            "product_id",
            "product__name",
            "product__barcode",
            "product__category_id",
            "product__category__name",
            "product__cost_price",
            "product__price",
            "unit_price",
            "sale__price_list_id",
        )
        .annotate(qty=Sum("quantity"), revenue=Sum("total"))
    )

    cost_base = Q(
        sale_item__sale__tenant=tenant,
        sale_item__sale__status=Sale.STATUS_COMPLETED,
        sale_item__sale__completed_at__date__gte=date_from,
        sale_item__sale__completed_at__date__lte=date_to,
    )
    cost_rows = (
        SaleItemBatch.objects.filter(cost_base)
        .values(
            "sale_item__product_id",
            "sale_item__unit_price",
            "sale_item__sale__price_list_id",
            "sale_item__product__price",
        )
        .annotate(cost=Sum(F("quantity") * F("unit_cost")))
    )

    cost_map: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    for r in cost_rows:
        pid = str(r["sale_item__product_id"])
        ch = classify_channel(
            unit_price=r["sale_item__unit_price"],
            selling_price=r["sale_item__product__price"],
            wholesale_prices=wh_by_product.get(pid, []),
            price_list_id=r["sale_item__sale__price_list_id"],
            selling_ids=selling_ids,
            wholesale_ids=wholesale_ids,
        )
        cost_map[(pid, ch)] += _d(r["cost"])

    products: dict[str, dict] = {}
    for r in sales_rows:
        pid = str(r["product_id"])
        ch = classify_channel(
            unit_price=r["unit_price"],
            selling_price=r["product__price"],
            wholesale_prices=wh_by_product.get(pid, []),
            price_list_id=r["sale__price_list_id"],
            selling_ids=selling_ids,
            wholesale_ids=wholesale_ids,
        )
        if channel != "all" and ch != channel:
            continue

        qty = _d(r["qty"], Q3)
        rev = _d(r["revenue"])
        # Cost shu kanal uchun umumiy — bir nechta unit_price bo'lsa proporsional emas,
        # lekin keyinroq qayta taqsimlash: avval to'liq costni bir marta olamiz.
        p = products.get(pid)
        if not p:
            p = {
                "product_id": pid,
                "name": r.get("product__name") or "",
                "barcode": r.get("product__barcode") or "",
                "category_id": str(r["product__category_id"] or "") or None,
                "category": r.get("product__category__name") or "",
                "cost_price": _d(r.get("product__cost_price")),
                "qty": ZERO,
                "retail_qty": ZERO,
                "wholesale_qty": ZERO,
                "retail_sales": ZERO,
                "wholesale_sales": ZERO,
                "retail_cost": ZERO,
                "wholesale_cost": ZERO,
                "retail_profit": ZERO,
                "wholesale_profit": ZERO,
                "sales": ZERO,
                "cost": ZERO,
                "profit": ZERO,
                "_retail_rev_for_cost": ZERO,
                "_wh_rev_for_cost": ZERO,
            }
            products[pid] = p

        p["qty"] += qty
        p["sales"] += rev
        if ch == "retail":
            p["retail_qty"] += qty
            p["retail_sales"] += rev
            p["_retail_rev_for_cost"] += rev
        else:
            p["wholesale_qty"] += qty
            p["wholesale_sales"] += rev
            p["_wh_rev_for_cost"] += rev

    # Cost: kanal bo'yicha FIFO; yo'qsa cost_price * qty
    for pid, p in products.items():
        r_cost = cost_map.get((pid, "retail"), ZERO)
        w_cost = cost_map.get((pid, "wholesale"), ZERO)
        if r_cost == 0 and p["retail_qty"] > 0:
            r_cost = (p["cost_price"] * p["retail_qty"]).quantize(Q2)
        if w_cost == 0 and p["wholesale_qty"] > 0:
            w_cost = (p["cost_price"] * p["wholesale_qty"]).quantize(Q2)

        p["retail_cost"] = r_cost
        p["wholesale_cost"] = w_cost
        p["cost"] = r_cost + w_cost
        p["retail_profit"] = p["retail_sales"] - r_cost
        p["wholesale_profit"] = p["wholesale_sales"] - w_cost
        p["profit"] = p["sales"] - p["cost"]
        p.pop("cost_price", None)
        p.pop("_retail_rev_for_cost", None)
        p.pop("_wh_rev_for_cost", None)

    # Katalogdagi barcha faol mahsulotlar (shu davrda sotilmaganlar ham — C guruh)
    if channel == "all":
        for row in Product.objects.filter(tenant=tenant, is_active=True).values(
            "id",
            "name",
            "barcode",
            "category_id",
            "category__name",
        ):
            pid = str(row["id"])
            if pid in products:
                continue
            products[pid] = {
                "product_id": pid,
                "name": row.get("name") or "",
                "barcode": row.get("barcode") or "",
                "category_id": str(row["category_id"] or "") or None,
                "category": row.get("category__name") or "",
                "qty": ZERO,
                "retail_qty": ZERO,
                "wholesale_qty": ZERO,
                "retail_sales": ZERO,
                "wholesale_sales": ZERO,
                "retail_cost": ZERO,
                "wholesale_cost": ZERO,
                "retail_profit": ZERO,
                "wholesale_profit": ZERO,
                "sales": ZERO,
                "cost": ZERO,
                "profit": ZERO,
            }

    items_list = list(products.values())
    if not items_list:
        return {
            "ok": True,
            "empty": True,
            "date_from": str(date_from),
            "date_to": str(date_to),
            "metric": metric,
            "channel": channel,
            "thresholds": {"A": float(a_max), "B": float(b_max)},
            "summary": {},
            "groups": {"A": {}, "B": {}, "C": {}},
            "charts": {},
            "items": [],
            "categories": [],
        }

    def sort_key(row):
        if metric == "profit":
            return row["profit"]
        if metric == "qty":
            return row["qty"]
        return row["sales"]

    items_list.sort(key=sort_key, reverse=True)

    # Pareto faqat ijobiy metrika bo'yicha (0 li mahsulotlar ulushni buzmasin)
    positive_total = sum((sort_key(x) for x in items_list if sort_key(x) > 0), ZERO)
    if positive_total <= 0:
        positive_total = Decimal("1")

    cumulative = ZERO
    sold_count = 0
    for row in items_list:
        val = sort_key(row)
        if val <= 0:
            row["share"] = 0.0
            row["cumulative_share"] = float(
                min(cumulative, Decimal("100")).quantize(Decimal("0.01"))
            )
            row["abc"] = "C"
        else:
            sold_count += 1
            share = val / positive_total * 100
            cumulative += share
            row["share"] = float(share.quantize(Decimal("0.01")))
            row["cumulative_share"] = float(
                min(cumulative, Decimal("100")).quantize(Decimal("0.01"))
            )
            if cumulative <= a_max:
                row["abc"] = "A"
            elif cumulative <= b_max:
                row["abc"] = "B"
            else:
                row["abc"] = "C"

        row["margin"] = _margin(row["profit"], row["sales"])
        row["retail_margin"] = _margin(row["retail_profit"], row["retail_sales"])
        row["wholesale_margin"] = _margin(row["wholesale_profit"], row["wholesale_sales"])
        row["is_loss"] = row["profit"] < 0
        row["sold"] = val > 0 or row["qty"] > 0

        for k in (
            "qty",
            "retail_qty",
            "wholesale_qty",
            "retail_sales",
            "wholesale_sales",
            "retail_cost",
            "wholesale_cost",
            "retail_profit",
            "wholesale_profit",
            "sales",
            "cost",
            "profit",
        ):
            row[k] = float(row[k])

    total_sales = sum((_d(x["sales"]) for x in items_list), ZERO)
    total_cost = sum((_d(x["cost"]) for x in items_list), ZERO)
    total_profit = sum((_d(x["profit"]) for x in items_list), ZERO)
    retail_sales = sum((_d(x["retail_sales"]) for x in items_list), ZERO)
    retail_profit = sum((_d(x["retail_profit"]) for x in items_list), ZERO)
    wholesale_sales = sum((_d(x["wholesale_sales"]) for x in items_list), ZERO)
    wholesale_profit = sum((_d(x["wholesale_profit"]) for x in items_list), ZERO)

    def group_block(letter: str) -> dict:
        rows = [x for x in items_list if x["abc"] == letter]
        g_sales = sum((_d(x["sales"]) for x in rows), ZERO)
        g_profit = sum((_d(x["profit"]) for x in rows), ZERO)
        g_qty = sum((_d(x["qty"], Q3) for x in rows), ZERO)
        return {
            "letter": letter,
            "count": len(rows),
            "sales": float(g_sales),
            "sales_display": _fmt_money(g_sales),
            "sales_share": float((g_sales / total_sales * 100).quantize(Decimal("0.01")))
            if total_sales
            else 0.0,
            "profit": float(g_profit),
            "profit_display": _fmt_money(g_profit),
            "profit_share": float((g_profit / total_profit * 100).quantize(Decimal("0.01")))
            if total_profit
            else 0.0,
            "qty": float(g_qty),
            "label": {
                "A": "Eng muhim mahsulotlar",
                "B": "O‘rtacha muhim",
                "C": "Kam ulushli",
            }[letter],
        }

    groups = {L: group_block(L) for L in "ABC"}
    cats = sorted({x["category"] for x in items_list if x.get("category")})

    summary = {
        "products_total": Product.objects.filter(tenant=tenant, is_active=True).count(),
        "products_sold": sold_count,
        "a_count": groups["A"]["count"],
        "b_count": groups["B"]["count"],
        "c_count": groups["C"]["count"],
        "total_sales": float(total_sales),
        "total_sales_display": _fmt_money(total_sales),
        "total_cost": float(total_cost),
        "total_cost_display": _fmt_money(total_cost),
        "total_profit": float(total_profit),
        "total_profit_display": _fmt_money(total_profit),
        "total_margin": _margin(total_profit, total_sales),
        "retail_sales": float(retail_sales),
        "retail_sales_display": _fmt_money(retail_sales),
        "retail_profit": float(retail_profit),
        "retail_profit_display": _fmt_money(retail_profit),
        "retail_margin": _margin(retail_profit, retail_sales),
        "wholesale_sales": float(wholesale_sales),
        "wholesale_sales_display": _fmt_money(wholesale_sales),
        "wholesale_profit": float(wholesale_profit),
        "wholesale_profit_display": _fmt_money(wholesale_profit),
        "wholesale_margin": _margin(wholesale_profit, wholesale_sales),
    }

    charts = {
        "abc_distribution": [{"letter": L, "count": groups[L]["count"]} for L in "ABC"],
        "sales_contribution": [
            {"letter": L, "value": groups[L]["sales_share"]} for L in "ABC"
        ],
        "profit_contribution": [
            {"letter": L, "value": groups[L]["profit_share"]} for L in "ABC"
        ],
        "retail_vs_wholesale": {
            "retail_sales": float(retail_sales),
            "wholesale_sales": float(wholesale_sales),
            "retail_profit": float(retail_profit),
            "wholesale_profit": float(wholesale_profit),
        },
    }

    return {
        "ok": True,
        "empty": len(items_list) == 0,
        "date_from": str(date_from),
        "date_to": str(date_to),
        "metric": metric,
        "channel": channel,
        "thresholds": {"A": float(a_max), "B": float(b_max)},
        "summary": summary,
        "groups": groups,
        "charts": charts,
        "items": items_list,
        "categories": cats,
    }


class AbcAnalysisView(APIView):
    """GET /api/sales/stats/abc/"""

    def get(self, request):
        tenant = request.user.tenant
        date_from, date_to, preset = _range_from_params(request.query_params)
        metric = request.query_params.get("metric") or "sales"
        channel = (
            request.query_params.get("channel")
            or request.query_params.get("sale_type")
            or "all"
        )
        try:
            a_max = Decimal(str(request.query_params.get("a_max") or ABC_THRESHOLDS["A"]))
            b_max = Decimal(str(request.query_params.get("b_max") or ABC_THRESHOLDS["B"]))
        except (InvalidOperation, TypeError, ValueError):
            a_max, b_max = ABC_THRESHOLDS["A"], ABC_THRESHOLDS["B"]

        payload = build_abc_payload(
            tenant,
            date_from=date_from,
            date_to=date_to,
            metric=metric,
            channel=channel,
            a_max=a_max,
            b_max=b_max,
        )
        payload["preset"] = preset
        return Response(payload)
