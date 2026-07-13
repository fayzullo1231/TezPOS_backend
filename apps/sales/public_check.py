"""Ommaviy elektron chek — autentifikatsiyasiz."""

from decimal import Decimal

from django.http import Http404, HttpResponse
from django.utils.html import escape
from django.views import View

from apps.accounts.models import Tenant

from .models import Sale


def _fmt_money(value) -> str:
    try:
        n = Decimal(str(value or 0))
    except Exception:
        n = Decimal("0")
    # 5000.00 → 5 000
    s = f"{n:,.0f}".replace(",", " ")
    return f"{s} so'm"


def _fmt_qty(value) -> str:
    try:
        n = Decimal(str(value or 0))
    except Exception:
        return "0"
    if n == n.to_integral_value():
        return str(int(n))
    return f"{n.normalize()}"


class PublicReceiptCheckView(View):
    """
    GET /check/<server_name>/<receipt_number>/
    Masalan: http://13.140.146.78:8000/check/xusanuz/4
    """

    def get(self, request, server_name: str, receipt_number: int):
        tenant = Tenant.objects.filter(server_name__iexact=server_name.strip()).first()
        if not tenant:
            raise Http404("Do'kon topilmadi")

        sale = (
            Sale.objects.filter(
                tenant=tenant,
                receipt_number=receipt_number,
                status=Sale.STATUS_COMPLETED,
            )
            .select_related("user", "customer")
            .prefetch_related("items")
            .order_by("-completed_at", "-created_at")
            .first()
        )
        if not sale:
            raise Http404("Chek topilmadi")

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

        html = f"""<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Chek № {sale.receipt_number} — {store}</title>
</head>
<body style="margin:0;background:#eef1f6;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a">
  <div style="max-width:480px;margin:24px auto;padding:0 12px 40px">
    <div style="background:#fff;border-radius:16px;box-shadow:0 8px 30px rgba(15,23,42,.08);overflow:hidden">
      <div style="padding:20px 20px 12px;border-bottom:1px solid #eef1f6;text-align:center">
        <div style="font-size:20px;font-weight:800;letter-spacing:-.02em">{store}</div>
        <div style="margin-top:4px;font-size:13px;color:#64748b">Elektron chek</div>
        <div style="margin-top:10px;font-size:18px;font-weight:700">№ {sale.receipt_number}</div>
        <div style="margin-top:4px;font-size:13px;color:#64748b">{when_s}</div>
      </div>
      <div style="padding:16px 20px;font-size:14px;line-height:1.5">
        <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:6px">
          <span style="color:#64748b">Mijoz</span><span style="font-weight:600">{customer}</span>
        </div>
        <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:6px">
          <span style="color:#64748b">To'lov</span><span style="font-weight:600">{escape(pay)}</span>
        </div>
        {f'<div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:6px"><span style="color:#64748b">Kassir</span><span>{cashier}</span></div>' if cashier else ''}
      </div>
      <div style="padding:0 12px 8px">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="color:#64748b;text-align:left">
              <th style="padding:8px 4px;font-weight:600">#</th>
              <th style="padding:8px 4px;font-weight:600">Mahsulot</th>
              <th style="padding:8px 4px;font-weight:600;text-align:right">Soni</th>
              <th style="padding:8px 4px;font-weight:600;text-align:right">Narx</th>
              <th style="padding:8px 4px;font-weight:600;text-align:right">Summa</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows) if rows else '<tr><td colspan="5" style="padding:16px;text-align:center;color:#94a3b8">Mahsulotlar yoq</td></tr>'}
          </tbody>
        </table>
      </div>
      <div style="padding:12px 20px 20px;border-top:1px solid #eef1f6">
        {(f'<div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:14px"><span style="color:#64748b">Chegirma</span><span>- {_fmt_money(sale.discount_amount)}</span></div>' if (sale.discount_amount or 0) > 0 else '')}
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px">
          <span style="font-size:15px;font-weight:700">Jami</span>
          <span style="font-size:22px;font-weight:800">{_fmt_money(sale.total)}</span>
        </div>
        {debt_block}
        <p style="margin:18px 0 0;text-align:center;font-size:12px;color:#94a3b8">TezPOS</p>
      </div>
    </div>
  </div>
</body>
</html>"""
        return HttpResponse(html, content_type="text/html; charset=utf-8")
