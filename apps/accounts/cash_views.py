from datetime import datetime
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sales.models import Sale, SaleReturn

from .models import CashTransaction, Shift
from .serializers import CashTransactionCreateSerializer


PAYMENT_LABELS = {
    "cash": "Naqd",
    "card": "Terminal",
    "mixed": "Aralash",
    "credit": "Qarzga",
}


def _parse_range(request):
    date_from = parse_date(request.query_params.get("date_from", ""))
    date_to = parse_date(request.query_params.get("date_to", ""))
    if not date_from or not date_to:
        today = timezone.localdate()
        date_from = date_to = today
    return date_from, date_to


def _dt_range(date_from, date_to):
    start = timezone.make_aware(datetime.combine(date_from, datetime.min.time()))
    end = timezone.make_aware(datetime.combine(date_to, datetime.max.time()))
    return start, end


def _cashier_name(user):
    if not user:
        return "—"
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return name or user.username


def _build_ledger_entries(tenant, start, end, search=""):
    entries = []

    sales = Sale.objects.filter(
        tenant=tenant,
        status=Sale.STATUS_COMPLETED,
        completed_at__gte=start,
        completed_at__lte=end,
    ).select_related("user")

    for sale in sales:
        amount = sale.paid_amount or Decimal("0")
        if amount <= 0:
            continue
        desc = (sale.customer_name or "Tashrif buyuruvchi").strip() or "Tashrif buyuruvchi"
        entries.append(
            {
                "id": f"sale-{sale.id}",
                "number": sale.receipt_number,
                "source": "sale",
                "created_at": sale.completed_at.isoformat(),
                "cashier": _cashier_name(sale.user),
                "category": "Mijozdan tushum",
                "amount": str(amount),
                "signed_amount": str(amount),
                "description": desc,
                "payment_method": sale.payment_type,
                "payment_label": PAYMENT_LABELS.get(sale.payment_type, sale.payment_type),
            }
        )

    returns = SaleReturn.objects.filter(
        tenant=tenant,
        status=SaleReturn.STATUS_COMPLETED,
        completed_at__gte=start,
        completed_at__lte=end,
    ).select_related("user")

    for ret in returns:
        amount = ret.paid_amount or ret.total or Decimal("0")
        if amount <= 0:
            continue
        desc = (ret.customer_name or "Qaytarish").strip() or "Qaytarish"
        entries.append(
            {
                "id": f"return-{ret.id}",
                "number": ret.receipt_number,
                "source": "return",
                "created_at": ret.completed_at.isoformat(),
                "cashier": _cashier_name(ret.user),
                "category": "Qaytarish",
                "amount": str(amount),
                "signed_amount": str(-amount),
                "description": desc,
                "payment_method": ret.payment_type,
                "payment_label": PAYMENT_LABELS.get(ret.payment_type, ret.payment_type),
            }
        )

    txs = CashTransaction.objects.filter(
        tenant=tenant,
        occurred_at__gte=start,
        occurred_at__lte=end,
    ).select_related("user")

    for tx in txs:
        signed = tx.amount if tx.transaction_type == CashTransaction.TYPE_INCOME else -tx.amount
        if tx.transaction_type == CashTransaction.TYPE_TRANSFER:
            signed = -tx.amount
        desc = (tx.description or "").strip()
        if tx.party_name:
            desc = f"{tx.party_name}" + (f" — {desc}" if desc else "")
        if not desc:
            desc = "—"
        entries.append(
            {
                "id": str(tx.id),
                "number": tx.number,
                "source": "manual",
                "created_at": tx.occurred_at.isoformat(),
                "cashier": _cashier_name(tx.user),
                "category": tx.category,
                "amount": str(tx.amount),
                "signed_amount": str(signed),
                "description": desc,
                "payment_method": tx.payment_method,
                "payment_label": PAYMENT_LABELS.get(tx.payment_method, tx.payment_method),
            }
        )

    if search:
        q = search.lower()
        entries = [
            e
            for e in entries
            if q in e["description"].lower()
            or q in e["category"].lower()
            or q in e["cashier"].lower()
            or q in str(e["number"])
        ]

    entries.sort(key=lambda e: e["created_at"], reverse=True)
    return entries


class CashLedgerView(APIView):
    def get(self, request):
        tenant = request.user.tenant
        date_from, date_to = _parse_range(request)
        start, end = _dt_range(date_from, date_to)
        search = request.query_params.get("search", "").strip()
        entries = _build_ledger_entries(tenant, start, end, search)
        return Response({"results": entries, "count": len(entries)})


class CashSummaryView(APIView):
    def get(self, request):
        tenant = request.user.tenant
        date_from, date_to = _parse_range(request)
        start, end = _dt_range(date_from, date_to)
        search = request.query_params.get("search", "").strip()

        last_closed = (
            Shift.objects.filter(tenant=tenant, status=Shift.STATUS_CLOSED)
            .order_by("-closed_at")
            .first()
        )
        opening = Decimal("0")
        if last_closed:
            opening = (last_closed.opening_cash or Decimal("0")) + (
                last_closed.opening_terminal or Decimal("0")
            )

        open_shift = Shift.objects.filter(
            tenant=tenant, user=request.user, status=Shift.STATUS_OPEN
        ).first()
        if open_shift:
            opening = (open_shift.opening_cash or Decimal("0")) + (
                open_shift.opening_terminal or Decimal("0")
            )

        sales_in = Sale.objects.filter(
            tenant=tenant,
            status=Sale.STATUS_COMPLETED,
            completed_at__gte=start,
            completed_at__lte=end,
        ).aggregate(s=Sum("paid_amount"))["s"] or Decimal("0")

        manual_in = CashTransaction.objects.filter(
            tenant=tenant,
            transaction_type=CashTransaction.TYPE_INCOME,
            occurred_at__gte=start,
            occurred_at__lte=end,
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0")

        returns_out = (
            SaleReturn.objects.filter(
                tenant=tenant,
                status=SaleReturn.STATUS_COMPLETED,
                completed_at__gte=start,
                completed_at__lte=end,
            ).aggregate(s=Sum("total"))["s"]
            or Decimal("0")
        )

        manual_out = CashTransaction.objects.filter(
            tenant=tenant,
            transaction_type__in=[
                CashTransaction.TYPE_EXPENSE,
                CashTransaction.TYPE_TRANSFER,
            ],
            occurred_at__gte=start,
            occurred_at__lte=end,
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0")

        income = sales_in + manual_in
        expense = returns_out + manual_out
        closing = opening + income - expense
        count = len(_build_ledger_entries(tenant, start, end, search))

        return Response(
            {
                "opening": str(opening),
                "income": str(income),
                "expense": str(expense),
                "closing": str(closing),
                "transaction_count": count,
                "date_from": str(date_from),
                "date_to": str(date_to),
            }
        )


class CashTransactionCreateView(APIView):
    def post(self, request):
        serializer = CashTransactionCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        tx = serializer.save()
        signed = tx.amount if tx.transaction_type == CashTransaction.TYPE_INCOME else -tx.amount
        if tx.transaction_type == CashTransaction.TYPE_TRANSFER:
            signed = -tx.amount
        return Response(
            {
                "id": str(tx.id),
                "number": tx.number,
                "source": "manual",
                "created_at": tx.occurred_at.isoformat(),
                "cashier": _cashier_name(tx.user),
                "category": tx.category,
                "amount": str(tx.amount),
                "signed_amount": str(signed),
                "description": (tx.party_name or tx.description or "—").strip() or "—",
                "payment_method": tx.payment_method,
                "payment_label": PAYMENT_LABELS.get(tx.payment_method, tx.payment_method),
            },
            status=status.HTTP_201_CREATED,
        )
