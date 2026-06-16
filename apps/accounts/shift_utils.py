from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import CashTransaction, Shift
from apps.sales.models import Sale, SaleReturn


def _dec(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def compute_shift_summary(shift: Shift) -> dict:
    tenant = shift.tenant
    sales_qs = Sale.objects.filter(
        shift=shift, tenant=tenant, status=Sale.STATUS_COMPLETED
    )
    sales_count = sales_qs.count()
    sales_total = _dec(sales_qs.aggregate(s=Sum("total"))["s"])

    cash_sales = _dec(
        sales_qs.filter(
            payment_type__in=[Sale.PAYMENT_CASH, Sale.PAYMENT_MIXED]
        ).aggregate(s=Sum("paid_amount"))["s"]
    )
    card_sales = _dec(
        sales_qs.filter(payment_type=Sale.PAYMENT_CARD).aggregate(s=Sum("paid_amount"))[
            "s"
        ]
    )

    returns_qs = SaleReturn.objects.filter(
        shift=shift, tenant=tenant, status=SaleReturn.STATUS_COMPLETED
    )
    returns_count = returns_qs.count()
    returns_total = _dec(returns_qs.aggregate(s=Sum("total"))["s"])

    cash_in = _dec(
        CashTransaction.objects.filter(
            shift=shift,
            tenant=tenant,
            transaction_type=CashTransaction.TYPE_INCOME,
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

    expected_cash = opening_cash + cash_sales + cash_in - returns_total - cash_out_cash
    expected_terminal = opening_terminal + card_sales - cash_out_card
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

    return {
        "sales_count": sales_count,
        "sales_total": str(sales_total.quantize(q)),
        "cash_sales": str(cash_sales.quantize(q)),
        "card_sales": str(card_sales.quantize(q)),
        "returns_count": returns_count,
        "returns_total": str(returns_total.quantize(q)),
        "cash_in": str(cash_in.quantize(q)),
        "cash_out": str(cash_out.quantize(q)),
        "expected_cash": str(expected_cash.quantize(q)),
        "expected_terminal": str(expected_terminal.quantize(q)),
        "expected_total": str(expected_total.quantize(q)),
        "duration_seconds": duration_seconds,
    }


def suggested_opening_balances(tenant) -> tuple[Decimal, Decimal]:
    last_closed = (
        Shift.objects.filter(tenant=tenant, status=Shift.STATUS_CLOSED)
        .order_by("-closed_at")
        .first()
    )
    if not last_closed:
        return Decimal("0"), Decimal("0")
    summary = compute_shift_summary(last_closed)
    return _dec(summary["expected_cash"]), _dec(summary["expected_terminal"])
