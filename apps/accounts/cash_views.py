from datetime import datetime
from decimal import Decimal

from django.db.models import Q, Sum
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

# Bitta so'rovda maksimal qator — zaif PC va tarmoq uchun
LEDGER_HARD_LIMIT = 1500


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


def _build_ledger_entries(tenant, start, end, search="", *, limit=LEDGER_HARD_LIMIT):
    """Yengil ledger — only() + DB filter; search bo'sh bo'lsa tezroq."""
    entries = []
    q = (search or "").strip()
    q_lower = q.lower()

    sales_qs = (
        Sale.objects.filter(
            tenant=tenant,
            status=Sale.STATUS_COMPLETED,
            completed_at__gte=start,
            completed_at__lte=end,
            paid_amount__gt=0,
        )
        .select_related("user")
        .only(
            "id",
            "receipt_number",
            "completed_at",
            "customer_name",
            "paid_amount",
            "payment_type",
            "user_id",
            "user__username",
            "user__first_name",
            "user__last_name",
        )
        .order_by("-completed_at")
    )
    if q:
        if q.isdigit():
            sales_qs = sales_qs.filter(
                Q(receipt_number=int(q)) | Q(customer_name__icontains=q)
            )
        else:
            sales_qs = sales_qs.filter(
                Q(customer_name__icontains=q)
                | Q(user__username__icontains=q)
                | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
            )
    for sale in sales_qs[:limit]:
        amount = sale.paid_amount or Decimal("0")
        desc = (sale.customer_name or "Tashrif buyuruvchi").strip() or "Tashrif buyuruvchi"
        entries.append(
            {
                "id": f"sale-{sale.id}",
                "number": sale.receipt_number,
                "source": "sale",
                "created_at": sale.completed_at.isoformat() if sale.completed_at else "",
                "cashier": _cashier_name(sale.user),
                "category": "Mijozdan tushum",
                "amount": str(amount),
                "signed_amount": str(amount),
                "description": desc,
                "payment_method": sale.payment_type,
                "payment_label": PAYMENT_LABELS.get(sale.payment_type, sale.payment_type),
            }
        )

    returns_qs = (
        SaleReturn.objects.filter(
            tenant=tenant,
            status=SaleReturn.STATUS_COMPLETED,
            completed_at__gte=start,
            completed_at__lte=end,
        )
        .select_related("user")
        .only(
            "id",
            "receipt_number",
            "completed_at",
            "customer_name",
            "paid_amount",
            "total",
            "payment_type",
            "user_id",
            "user__username",
            "user__first_name",
            "user__last_name",
        )
        .order_by("-completed_at")
    )
    if q:
        if q.isdigit():
            returns_qs = returns_qs.filter(
                Q(receipt_number=int(q)) | Q(customer_name__icontains=q)
            )
        else:
            returns_qs = returns_qs.filter(
                Q(customer_name__icontains=q)
                | Q(user__username__icontains=q)
                | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
            )
    for ret in returns_qs[:limit]:
        amount = ret.paid_amount or ret.total or Decimal("0")
        if amount <= 0:
            continue
        desc = (ret.customer_name or "Qaytarish").strip() or "Qaytarish"
        entries.append(
            {
                "id": f"return-{ret.id}",
                "number": ret.receipt_number,
                "source": "return",
                "created_at": ret.completed_at.isoformat() if ret.completed_at else "",
                "cashier": _cashier_name(ret.user),
                "category": "Qaytarish",
                "amount": str(amount),
                "signed_amount": str(-amount),
                "description": desc,
                "payment_method": ret.payment_type,
                "payment_label": PAYMENT_LABELS.get(ret.payment_type, ret.payment_type),
            }
        )

    txs_qs = (
        CashTransaction.objects.filter(
            tenant=tenant,
            occurred_at__gte=start,
            occurred_at__lte=end,
        )
        .select_related("user")
        .only(
            "id",
            "number",
            "occurred_at",
            "amount",
            "transaction_type",
            "category",
            "description",
            "party_name",
            "payment_method",
            "user_id",
            "user__username",
            "user__first_name",
            "user__last_name",
        )
        .order_by("-occurred_at")
    )
    if q:
        if q.isdigit():
            txs_qs = txs_qs.filter(
                Q(number=int(q))
                | Q(description__icontains=q)
                | Q(category__icontains=q)
                | Q(party_name__icontains=q)
            )
        else:
            txs_qs = txs_qs.filter(
                Q(description__icontains=q)
                | Q(category__icontains=q)
                | Q(party_name__icontains=q)
                | Q(user__username__icontains=q)
                | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
            )
    for tx in txs_qs[:limit]:
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
                "created_at": tx.occurred_at.isoformat() if tx.occurred_at else "",
                "cashier": _cashier_name(tx.user),
                "category": tx.category,
                "amount": str(tx.amount),
                "signed_amount": str(signed),
                "description": desc,
                "payment_method": tx.payment_method,
                "payment_label": PAYMENT_LABELS.get(tx.payment_method, tx.payment_method),
            }
        )

    # Python search faqat qoldiq bo'lsa (DB filter yetarli emas)
    if q_lower and not q.isdigit():
        entries = [
            e
            for e in entries
            if q_lower in e["description"].lower()
            or q_lower in e["category"].lower()
            or q_lower in e["cashier"].lower()
            or q_lower in str(e["number"])
        ]

    entries.sort(key=lambda e: e["created_at"] or "", reverse=True)
    if len(entries) > limit:
        entries = entries[:limit]
    return entries


def _ledger_count(tenant, start, end, search=""):
    """To'liq ledger qurmasdan soni — summary uchun."""
    q = (search or "").strip()
    sales_qs = Sale.objects.filter(
        tenant=tenant,
        status=Sale.STATUS_COMPLETED,
        completed_at__gte=start,
        completed_at__lte=end,
        paid_amount__gt=0,
    )
    returns_qs = SaleReturn.objects.filter(
        tenant=tenant,
        status=SaleReturn.STATUS_COMPLETED,
        completed_at__gte=start,
        completed_at__lte=end,
    ).filter(Q(paid_amount__gt=0) | Q(total__gt=0))
    txs_qs = CashTransaction.objects.filter(
        tenant=tenant,
        occurred_at__gte=start,
        occurred_at__lte=end,
    )
    if q:
        if q.isdigit():
            sales_qs = sales_qs.filter(
                Q(customer_name__icontains=q) | Q(receipt_number=int(q))
            )
            returns_qs = returns_qs.filter(
                Q(customer_name__icontains=q) | Q(receipt_number=int(q))
            )
            txs_qs = txs_qs.filter(
                Q(description__icontains=q)
                | Q(category__icontains=q)
                | Q(party_name__icontains=q)
                | Q(number=int(q))
            )
        else:
            sales_qs = sales_qs.filter(Q(customer_name__icontains=q))
            returns_qs = returns_qs.filter(Q(customer_name__icontains=q))
            txs_qs = txs_qs.filter(
                Q(description__icontains=q)
                | Q(category__icontains=q)
                | Q(party_name__icontains=q)
            )
    return (
        sales_qs.count()
        + returns_qs.count()
        + txs_qs.count()
    )


class CashLedgerView(APIView):
    def get(self, request):
        tenant = request.user.tenant
        date_from, date_to = _parse_range(request)
        start, end = _dt_range(date_from, date_to)
        search = request.query_params.get("search", "").strip()
        try:
            limit = int(request.query_params.get("limit") or LEDGER_HARD_LIMIT)
        except (TypeError, ValueError):
            limit = LEDGER_HARD_LIMIT
        limit = max(50, min(limit, LEDGER_HARD_LIMIT))
        entries = _build_ledger_entries(tenant, start, end, search, limit=limit)
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
            .only("opening_cash", "opening_terminal", "closed_at")
            .first()
        )
        opening = Decimal("0")
        if last_closed:
            opening = (last_closed.opening_cash or Decimal("0")) + (
                last_closed.opening_terminal or Decimal("0")
            )

        open_shift = (
            Shift.objects.filter(
                tenant=tenant, user=request.user, status=Shift.STATUS_OPEN
            )
            .only("opening_cash", "opening_terminal")
            .first()
        )
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
        # Eski: to'liq ledger qurilardi — endi faqat COUNT
        count = _ledger_count(tenant, start, end, search)

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
