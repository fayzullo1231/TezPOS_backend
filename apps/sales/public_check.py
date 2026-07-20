"""Ommaviy elektron chek — autentifikatsiyasiz."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.http import HttpResponse
from django.utils.html import escape
from django.views import View

from apps.accounts.models import Tenant

from .models import CustomerDebtPayment, Sale


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


def _html_page(title: str, body: str, status: int = 200) -> HttpResponse:
    html = f"""<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{escape(title)}</title>
</head>
<body style="margin:0;background:#eef1f6;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a">
  <div style="max-width:480px;margin:40px auto;padding:0 16px">
    {body}
  </div>
</body>
</html>"""
    return HttpResponse(html, status=status, content_type="text/html; charset=utf-8")


def _not_found(title: str, detail: str) -> HttpResponse:
    return _html_page(
        title,
        f"""
        <div style="background:#fff;border-radius:16px;padding:28px 22px;text-align:center;box-shadow:0 8px 30px rgba(15,23,42,.08)">
          <div style="font-size:18px;font-weight:700;margin-bottom:8px">{escape(title)}</div>
          <div style="color:#64748b;font-size:14px">{detail}</div>
        </div>
        """,
        status=404,
    )


class PublicReceiptCheckView(View):
    """
    GET /check/<server_name>/<ref>/
    ref = sale UUID | payment UUID | receipt_number (int)
    Masalan: https://tez-pos.uz/check/xusanuz/a1b2c3d4-.../
             https://tez-pos.uz/check/xusanuz/4/
    """

    def get(self, request, server_name: str, ref: str):
        slug = (server_name or "").strip()
        tenant = Tenant.objects.filter(server_name__iexact=slug).first()
        if not tenant:
            return _not_found(
                "Do'kon topilmadi",
                f"Server: <code>{escape(slug)}</code>",
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
                .prefetch_related("items")
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
                .prefetch_related("items")
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

        if payment:
            return self._render_payment(tenant, payment)
        if sale:
            return self._render_sale(tenant, sale)
        return _not_found(
            "Chek topilmadi",
            f"{escape(tenant.display_name or tenant.server_name)} — <code>{escape(ref)}</code>",
        )

    def _render_payment(self, tenant, payment: CustomerDebtPayment) -> HttpResponse:
        store = escape(tenant.display_name or tenant.server_name)
        customer = escape(payment.customer.name if payment.customer_id else "—")
        when = payment.created_at
        when_s = when.strftime("%d.%m.%Y %H:%M") if when else "—"
        paid = payment.amount or Decimal("0")
        balance = payment.balance_after
        if balance is None and payment.customer_id:
            balance = payment.customer.debt
        body = f"""
    <div style="background:#fff;border-radius:16px;box-shadow:0 8px 30px rgba(15,23,42,.08);overflow:hidden">
      <div style="padding:20px 20px 12px;border-bottom:1px solid #eef1f6;text-align:center">
        <div style="font-size:20px;font-weight:800">{store}</div>
        <div style="margin-top:6px;color:#64748b;font-size:13px">Qarz to'lovi № {payment.receipt_number}</div>
      </div>
      <div style="padding:16px 20px;font-size:13px;color:#475569;line-height:1.6">
        <div style="display:flex;justify-content:space-between"><span>Sana</span><strong style="color:#0f172a">{when_s}</strong></div>
        <div style="display:flex;justify-content:space-between"><span>Mijoz</span><strong style="color:#0f172a">{customer}</strong></div>
        <div style="display:flex;justify-content:space-between"><span>Turi</span><strong style="color:#0f172a">Qarz to'lovi</strong></div>
      </div>
      <div style="padding:16px 20px 20px;border-top:1px solid #eef1f6">
        <div style="margin-top:4px;padding:12px;border-radius:12px;background:#ecfdf5;border:1px solid #a7f3d0">
          <div style="display:flex;justify-content:space-between;margin-bottom:6px">
            <span style="color:#065f46">Qarz</span>
            <strong style="color:#047857">{_fmt_money(-paid)}</strong>
          </div>
          <div style="display:flex;justify-content:space-between">
            <span style="color:#065f46">Qoldiq</span>
            <strong style="color:#047857">{_fmt_money(balance)}</strong>
          </div>
        </div>
      </div>
    </div>
    <div style="text-align:center;color:#94a3b8;font-size:11px;margin-top:16px">TezPOS</div>
        """
        return _html_page(f"To'lov № {payment.receipt_number} — {store}", body)

    def _render_sale(self, tenant, sale: Sale) -> HttpResponse:
        store = escape(tenant.display_name or tenant.server_name)
        cashier = ""
        if sale.user_id:
            u = sale.user
            cashier = escape(
                (getattr(u, "first_name", None) or "")
                or (getattr(u, "username", None) or "")
            )
        customer = escape(sale.customer_name or "—")
        when = sale.completed_at or sale.created_at
        when_s = when.strftime("%d.%m.%Y %H:%M") if when else "—"

        pay_map = {
            Sale.PAYMENT_CASH: "Naqd",
            Sale.PAYMENT_CARD: "Terminal",
            Sale.PAYMENT_MIXED: "Aralash",
            Sale.PAYMENT_CREDIT: "Qarzga",
        }
        pay = pay_map.get(sale.payment_type, sale.payment_type)

        rows = []
        for idx, it in enumerate(sale.items.all(), start=1):
            rows.append(
                "<tr>"
                f"<td style='padding:8px 4px;border-bottom:1px solid #eee;color:#64748b'>{idx}</td>"
                f"<td style='padding:8px 4px;border-bottom:1px solid #eee'>{escape(it.product_name)}</td>"
                f"<td style='padding:8px 4px;border-bottom:1px solid #eee;text-align:right'>{_fmt_qty(it.quantity)}</td>"
                f"<td style='padding:8px 4px;border-bottom:1px solid #eee;text-align:right'>{_fmt_money(it.unit_price)}</td>"
                f"<td style='padding:8px 4px;border-bottom:1px solid #eee;text-align:right;font-weight:600'>{_fmt_money(it.total)}</td>"
                "</tr>"
            )

        debt_block = ""
        if sale.payment_type == Sale.PAYMENT_CREDIT or (sale.debt_amount or 0) > 0:
            balance = "—"
            if sale.customer_id and sale.customer:
                balance = _fmt_money(sale.customer.debt)
            debt_block = f"""
            <div style="margin-top:16px;padding:12px;border-radius:12px;background:#fff7ed;border:1px solid #fed7aa">
              <div style="display:flex;justify-content:space-between;margin-bottom:6px">
                <span style="color:#9a3412">Qarz</span>
                <strong style="color:#c2410c">{_fmt_money(sale.debt_amount)}</strong>
              </div>
              <div style="display:flex;justify-content:space-between">
                <span style="color:#9a3412">Qoldiq</span>
                <strong style="color:#c2410c">{balance}</strong>
              </div>
            </div>
            """

        body = f"""
    <div style="background:#fff;border-radius:16px;box-shadow:0 8px 30px rgba(15,23,42,.08);overflow:hidden">
      <div style="padding:20px 20px 12px;border-bottom:1px solid #eef1f6;text-align:center">
        <div style="font-size:20px;font-weight:800;letter-spacing:-.02em">{store}</div>
        <div style="margin-top:6px;color:#64748b;font-size:13px">Elektron chek № {sale.receipt_number}</div>
      </div>
      <div style="padding:16px 20px;font-size:13px;color:#475569;line-height:1.6">
        <div style="display:flex;justify-content:space-between"><span>Sana</span><strong style="color:#0f172a">{when_s}</strong></div>
        <div style="display:flex;justify-content:space-between"><span>Kassir</span><strong style="color:#0f172a">{cashier or "—"}</strong></div>
        <div style="display:flex;justify-content:space-between"><span>Mijoz</span><strong style="color:#0f172a">{customer}</strong></div>
        <div style="display:flex;justify-content:space-between"><span>To'lov</span><strong style="color:#0f172a">{pay}</strong></div>
      </div>
      <div style="padding:0 12px 8px">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="color:#94a3b8;text-align:left">
              <th style="padding:8px 4px;font-weight:600">#</th>
              <th style="padding:8px 4px;font-weight:600">Mahsulot</th>
              <th style="padding:8px 4px;font-weight:600;text-align:right">Soni</th>
              <th style="padding:8px 4px;font-weight:600;text-align:right">Narx</th>
              <th style="padding:8px 4px;font-weight:600;text-align:right">Summa</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows) if rows else "<tr><td colspan='5' style='padding:12px;color:#94a3b8;text-align:center'>Mahsulot yo'q</td></tr>"}
          </tbody>
        </table>
      </div>
      <div style="padding:16px 20px 20px;border-top:1px solid #eef1f6">
        <div style="display:flex;justify-content:space-between;font-size:15px;margin-bottom:6px">
          <span style="color:#64748b">Jami</span>
          <strong>{_fmt_money(sale.total)}</strong>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:13px;color:#64748b">
          <span>To'langan</span><span>{_fmt_money(sale.paid_amount)}</span>
        </div>
        {debt_block}
      </div>
    </div>
    <div style="text-align:center;color:#94a3b8;font-size:11px;margin-top:16px">TezPOS</div>
        """
        return _html_page(f"Chek № {sale.receipt_number} — {store}", body)
