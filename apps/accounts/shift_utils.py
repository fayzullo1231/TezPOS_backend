"""Smena hisobi — kassa kutilgan qoldiq (naqd + terminal)."""

from __future__ import annotations

import re
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import CashTransaction, Shift
from apps.sales.models import CustomerDebtPayment, Sale, SaleReturn

_SPLIT_RE = re.compile(
    r"Naqd:\s*([\d.,]+).*?Terminal:\s*([\d.,]+)",
    re.IGNORECASE | re.DOTALL,
)


def _dec(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return Decimal(str(val).replace(" ", "").replace(",", "."))


def _parse_mixed_split(comment: str, paid: Decimal) -> tuple[Decimal, Decimal] | None:
    """Comment ichidagi 'Naqd: X; Terminal: Y' — aralash to'lovni ajratish."""
    if not comment or paid <= 0:
        return None
    m = _SPLIT_RE.search(comment)
    if not m:
        return None
    cash = _dec(m.group(1))
    card = _dec(m.group(2))
    if cash < 0 or card < 0:
        return None
    # Agar comment summalari paid bilan taxminan mos kelsa — ishonamiz
    if abs((cash + card) - paid) > Decimal("1"):
        return None
    return cash, card


def _sale_cash_card(sale: Sale) -> tuple[Decimal, Decimal]:
    paid = _dec(sale.paid_amount)
    pt = sale.payment_type or Sale.PAYMENT_CASH
    if pt == Sale.PAYMENT_CARD:
        return Decimal("0"), paid
    if pt == Sale.PAYMENT_CREDIT:
        # Qarzga: faqat haqiqatda to'langan qism (agar bor)
        return paid, Decimal("0")
    if pt == Sale.PAYMENT_MIXED:
        split = _parse_mixed_split(sale.comment or "", paid)
        if split:
            return split
        # Fallback: butun paid naqdga (yopishda jami solishtiriladi)
        return paid, Decimal("0")
    # cash
    return paid, Decimal("0")


def _return_cash_card(ret: SaleReturn) -> tuple[Decimal, Decimal]:
    amount = _dec(ret.paid_amount) or _dec(ret.total)
    pt = ret.payment_type or SaleReturn.PAYMENT_CASH
    if pt == SaleReturn.PAYMENT_CARD:
        return Decimal("0"), amount
    if pt == SaleReturn.PAYMENT_MIXED:
        split = _parse_mixed_split(ret.comment or "", amount)
        if split:
            return split
        return amount, Decimal("0")
    if pt == SaleReturn.PAYMENT_CREDIT:
        return Decimal("0"), Decimal("0")
    return amount, Decimal("0")


def compute_shift_summary(shift: Shift, *, floor_zero: bool = True) -> dict:
    tenant = shift.tenant
    sales_qs = Sale.objects.filter(
        shift=shift, tenant=tenant, status=Sale.STATUS_COMPLETED
    )
    sales_count = sales_qs.count()
    sales_total = _dec(sales_qs.aggregate(s=Sum("total"))["s"])

    cash_sales = Decimal("0")
    card_sales = Decimal("0")
    for sale in sales_qs.only(
        "paid_amount", "payment_type", "comment", "debt_amount"
    ):
        c, t = _sale_cash_card(sale)
        cash_sales += c
        card_sales += t

    # Qarzga berilgan (kassaga TA'SIR QILMAYDI)
    credit_qs = sales_qs.filter(debt_amount__gt=0)
    credit_sales_count = credit_qs.count()
    debt_total = _dec(credit_qs.aggregate(s=Sum("debt_amount"))["s"])

    returns_qs = SaleReturn.objects.filter(
        shift=shift, tenant=tenant, status=SaleReturn.STATUS_COMPLETED
    )
    returns_count = returns_qs.count()
    returns_total = _dec(returns_qs.aggregate(s=Sum("total"))["s"])
    cash_returns = Decimal("0")
    card_returns = Decimal("0")
    for ret in returns_qs.only("paid_amount", "total", "payment_type", "comment"):
        c, t = _return_cash_card(ret)
        cash_returns += c
        card_returns += t

    # Qarz undirish (shu smenada to'langan). [qarz+] — qo'shish, undirish emas.
    debt_pay_qs = CustomerDebtPayment.objects.filter(
        shift=shift, tenant=tenant
    ).exclude(note__startswith="[qarz+]")
    debt_collections_count = debt_pay_qs.count()
    debt_collections_cash = _dec(
        debt_pay_qs.filter(payment_type=CustomerDebtPayment.PAYMENT_CASH).aggregate(
            s=Sum("amount")
        )["s"]
    )
    debt_collections_card = _dec(
        debt_pay_qs.filter(payment_type=CustomerDebtPayment.PAYMENT_CARD).aggregate(
            s=Sum("amount")
        )["s"]
    )
    debt_collections_total = debt_collections_cash + debt_collections_card

    cash_in = _dec(
        CashTransaction.objects.filter(
            shift=shift,
            tenant=tenant,
            transaction_type=CashTransaction.TYPE_INCOME,
            payment_method=CashTransaction.PAYMENT_CASH,
        ).aggregate(s=Sum("amount"))["s"]
    )
    cash_in_card = _dec(
        CashTransaction.objects.filter(
            shift=shift,
            tenant=tenant,
            transaction_type=CashTransaction.TYPE_INCOME,
            payment_method=CashTransaction.PAYMENT_CARD,
        ).aggregate(s=Sum("amount"))["s"]
    )

    expense_qs = CashTransaction.objects.filter(
        shift=shift,
        tenant=tenant,
        transaction_type__in=[
            CashTransaction.TYPE_EXPENSE,
            CashTransaction.TYPE_TRANSFER,
        ],
    )
    cash_out_cash = _dec(
        expense_qs.filter(payment_method=CashTransaction.PAYMENT_CASH).aggregate(
            s=Sum("amount")
        )["s"]
    )
    cash_out_card = _dec(
        expense_qs.filter(payment_method=CashTransaction.PAYMENT_CARD).aggregate(
            s=Sum("amount")
        )["s"]
    )
    cash_out = cash_out_cash + cash_out_card

    opening_cash = _dec(shift.opening_cash)
    opening_terminal = _dec(shift.opening_terminal)

    expected_cash = (
        opening_cash
        + cash_sales
        + debt_collections_cash
        + cash_in
        - cash_returns
        - cash_out_cash
    )
    expected_terminal = (
        opening_terminal
        + card_sales
        + debt_collections_card
        + cash_in_card
        - card_returns
        - cash_out_card
    )
    raw_cash, raw_terminal = expected_cash, expected_terminal
    if floor_zero:
        if expected_cash < 0:
            expected_cash = Decimal("0")
        if expected_terminal < 0:
            expected_terminal = Decimal("0")
    expected_total = expected_cash + expected_terminal

    duration_seconds = 0
    if shift.opened_at:
        end = shift.closed_at or timezone.now()
        duration_seconds = max(0, int((end - shift.opened_at).total_seconds()))

    q = Decimal("0.01")

    closing_cash = shift.closing_cash
    closing_terminal = shift.closing_terminal
    result = {
        "sales_count": sales_count,
        "sales_total": str(sales_total.quantize(q)),
        "cash_sales": str(cash_sales.quantize(q)),
        "card_sales": str(card_sales.quantize(q)),
        "credit_sales_count": credit_sales_count,
        "debt_total": str(debt_total.quantize(q)),
        "debt_collections_count": debt_collections_count,
        "debt_collections_cash": str(debt_collections_cash.quantize(q)),
        "debt_collections_card": str(debt_collections_card.quantize(q)),
        "debt_collections_total": str(debt_collections_total.quantize(q)),
        "returns_count": returns_count,
        "returns_total": str(returns_total.quantize(q)),
        "cash_in": str((cash_in + cash_in_card).quantize(q)),
        "cash_out": str(cash_out.quantize(q)),
        "expected_cash": str(expected_cash.quantize(q)),
        "expected_terminal": str(expected_terminal.quantize(q)),
        "expected_total": str(expected_total.quantize(q)),
        "raw_expected_cash": str(raw_cash.quantize(q)),
        "raw_expected_terminal": str(raw_terminal.quantize(q)),
        "duration_seconds": duration_seconds,
    }
    if closing_cash is not None:
        result["closing_cash"] = str(_dec(closing_cash).quantize(q))
    if closing_terminal is not None:
        result["closing_terminal"] = str(_dec(closing_terminal).quantize(q))
    if shift.variance_cash is not None:
        result["variance_cash"] = str(_dec(shift.variance_cash).quantize(q))
    if shift.variance_terminal is not None:
        result["variance_terminal"] = str(_dec(shift.variance_terminal).quantize(q))
    if shift.variance_reason:
        result["variance_reason"] = shift.variance_reason
    return result


def suggested_opening_balances(tenant) -> tuple[Decimal, Decimal]:
    """Oxirgi yopilgan smenaning kutilgan qoldig'i (taklif)."""
    last_closed = (
        Shift.objects.filter(tenant=tenant, status=Shift.STATUS_CLOSED)
        .order_by("-closed_at")
        .first()
    )
    if not last_closed:
        return Decimal("0"), Decimal("0")
    # Agar sanagan yopish saqlangan bo'lsa — keyingi ochish uchun shuni taklif qilamiz
    if last_closed.closing_cash is not None or last_closed.closing_terminal is not None:
        return _dec(last_closed.closing_cash), _dec(last_closed.closing_terminal)
    summary = compute_shift_summary(last_closed)
    return _dec(summary["expected_cash"]), _dec(summary["expected_terminal"])


def default_opening_balances(tenant) -> tuple[Decimal, Decimal]:
    return _dec(getattr(tenant, "default_opening_cash", 0)), _dec(
        getattr(tenant, "default_opening_terminal", 0)
    )
