"""Ommaviy chek ma'lumoti — faqat JSON API (HTML tezpos_site da).

GET /api/public/check/<server_name>/<ref>/
Brauzer /check/... so'rovlari https://tez-pos.uz/check/... ga yo'naltiriladi.
"""

from __future__ import annotations

import os
from decimal import Decimal
from uuid import UUID

from django.db.models import Prefetch
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.html import escape
from django.views import View

from apps.accounts.models import Tenant

from .models import CustomerDebtPayment, Sale, SaleItem

_ITEMS_PREFETCH = Prefetch(
    "items",
    queryset=SaleItem.objects.order_by("sort_order", "id"),
)

PUBLIC_CHECK_SITE_BASE = (
    os.getenv("PUBLIC_CHECK_SITE_BASE", "https://tez-pos.uz").rstrip("/")
)


def _fmt_money(value) -> str:
    try:
        n = Decimal(str(value or 0))
    except Exception:
        n = Decimal("0")
    sign = "-" if n < 0 else ""
    s = f"{abs(n):,.0f}".replace(",", " ")
    return f"{sign}{s} so'm"


def _fmt_qty(value) -> str:
    try:
        n = Decimal(str(value or 0))
    except Exception:
        return "0"
    if n == n.to_integral_value():
        return str(int(n))
    return f"{n.normalize()}"


def _wants_json(request) -> bool:
    if (request.GET.get("format") or "").strip().lower() == "json":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept and "text/html" not in accept


class PublicCheckRedirectView(View):
    """Eski /check/... linklar → tezpos_site (domen)."""

    def get(self, request, server_name: str, ref: str):
        slug = (server_name or "").strip()
        ref = (ref or "").strip().rstrip("/")
        if _wants_json(request):
            return PublicCheckJsonView.as_view()(request, server_name=slug, ref=ref)
        return HttpResponseRedirect(f"{PUBLIC_CHECK_SITE_BASE}/check/{slug}/{ref}/")


class PublicCheckJsonView(View):
    """JSON ma'lumot — HTML dizayn tezpos_site da."""

    def get(self, request, server_name: str, ref: str):
        slug = (server_name or "").strip()
        tenant = Tenant.objects.filter(server_name__iexact=slug).first()
        if not tenant:
            return JsonResponse(
                {
                    "ok": False,
                    "kind": "not_found",
                    "title": "Do'kon topilmadi",
                    "store_name": "TezPOS",
                    "subtitle": "Elektron chek",
                    "empty_title": "Do'kon topilmadi",
                    "empty_detail": f"Server: <code>{escape(slug)}</code>",
                },
                status=404,
                json_dumps_params={"ensure_ascii": False},
            )

        ref = (ref or "").strip().rstrip("/")
        payment = None
        sale = None

        try:
            uid = UUID(str(ref))
        except Exception:
            uid = None

        if uid is not None:
            sale = (
                Sale.objects.filter(
                    tenant=tenant,
                    id=uid,
                    status=Sale.STATUS_COMPLETED,
                )
                .select_related("user", "customer")
                .prefetch_related(_ITEMS_PREFETCH)
                .first()
            )
            if not sale:
                payment = (
                    CustomerDebtPayment.objects.filter(tenant=tenant, id=uid)
                    .select_related("customer", "user")
                    .first()
                )
        elif ref.isdigit():
            num = int(ref)
            sale = (
                Sale.objects.filter(
                    tenant=tenant,
                    receipt_number=num,
                    status=Sale.STATUS_COMPLETED,
                )
                .select_related("user", "customer")
                .prefetch_related(_ITEMS_PREFETCH)
                .order_by("-completed_at", "-created_at")
                .first()
            )
            if not sale:
                payment = (
                    CustomerDebtPayment.objects.filter(
                        tenant=tenant, receipt_number=num
                    )
                    .select_related("customer", "user")
                    .order_by("-created_at")
                    .first()
                )

        store = tenant.display_name or tenant.server_name

        if payment:
            return JsonResponse(
                self._payment_payload(store, payment),
                json_dumps_params={"ensure_ascii": False},
            )
        if sale:
            return JsonResponse(
                self._sale_payload(store, sale),
                json_dumps_params={"ensure_ascii": False},
            )

        return JsonResponse(
            {
                "ok": False,
                "kind": "not_found",
                "title": "Chek topilmadi",
                "store_name": store,
                "subtitle": "Elektron chek",
                "empty_title": "Chek topilmadi",
                "empty_detail": f"{escape(store)} — <code>{escape(ref)}</code>",
            },
            status=404,
            json_dumps_params={"ensure_ascii": False},
        )

    def _payment_payload(self, store, payment: CustomerDebtPayment) -> dict:
        customer = payment.customer.name if payment.customer_id else "—"
        when = payment.created_at
        when_s = when.strftime("%d.%m.%Y %H:%M") if when else "—"
        paid = payment.amount or Decimal("0")
        balance = payment.balance_after
        if balance is None and payment.customer_id:
            balance = payment.customer.debt
        return {
            "ok": True,
            "title": f"To'lov № {payment.receipt_number} — {store}",
            "store_name": store,
            "subtitle": f"Qarz to'lovi № {payment.receipt_number}",
            "kind": "payment",
            "meta_rows": [
                {"label": "Sana", "value": when_s},
                {"label": "Mijoz", "value": customer},
                {"label": "Turi", "value": "Qarz to'lovi"},
            ],
            "debt_amount": _fmt_money(-paid),
            "debt_balance": _fmt_money(balance),
        }

    def _sale_payload(self, store, sale: Sale) -> dict:
        cashier = ""
        if sale.user_id:
            u = sale.user
            cashier = (
                (getattr(u, "first_name", None) or "")
                or (getattr(u, "username", None) or "")
            )
        customer = sale.customer_name or "—"
        when = sale.completed_at or sale.created_at
        when_s = when.strftime("%d.%m.%Y %H:%M") if when else "—"

        pay_map = {
            Sale.PAYMENT_CASH: "Naqd",
            Sale.PAYMENT_CARD: "Terminal",
            Sale.PAYMENT_MIXED: "Aralash",
            Sale.PAYMENT_CREDIT: "Qarzga",
        }
        pay = pay_map.get(sale.payment_type, sale.payment_type)

        items = [
            {
                "name": it.product_name,
                "qty": _fmt_qty(it.quantity),
                "price": _fmt_money(it.unit_price),
                "total": _fmt_money(it.total),
            }
            for it in sale.items.all()
        ]

        show_debt = sale.payment_type == Sale.PAYMENT_CREDIT or (sale.debt_amount or 0) > 0
        debt_balance = "—"
        if show_debt and sale.customer_id and sale.customer:
            debt_balance = _fmt_money(sale.customer.debt)

        return {
            "ok": True,
            "title": f"Chek № {sale.receipt_number} — {store}",
            "store_name": store,
            "subtitle": f"Elektron chek № {sale.receipt_number}",
            "kind": "sale",
            "meta_rows": [
                {"label": "Sana", "value": when_s},
                {"label": "Kassir", "value": cashier or "—"},
                {"label": "Mijoz", "value": customer},
                {"label": "To'lov", "value": pay},
            ],
            "items": items,
            "total": _fmt_money(sale.total),
            "paid": _fmt_money(sale.paid_amount),
            "show_debt": show_debt,
            "debt_amount": _fmt_money(sale.debt_amount),
            "debt_balance": debt_balance,
        }


# Eski importlar uchun alias
PublicReceiptCheckView = PublicCheckRedirectView
