"""Mijoz qarz qoldig'ini yangilash yordamchilari."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from .models import Customer, CustomerDebtPayment, Sale, SaleReturn

_WALK_IN = frozenset(
    {
        "",
        "tashrif buyuruvchi",
        "tashrifbuyuruvchi",
        "mehmon",
        "guest",
        "walk-in",
        "walkin",
        "mijoz",
    }
)


def is_walk_in_name(name: str | None) -> bool:
    key = " ".join(str(name or "").strip().lower().split())
    return key in _WALK_IN


def resolve_customer(
    tenant,
    *,
    customer: Customer | None = None,
    customer_id=None,
    customer_name: str = "",
    phone: str = "",
    create_if_missing: bool = False,
) -> Customer | None:
    """Mijozni id yoki nom bo'yicha topish; kerak bo'lsa yaratish."""
    if customer is not None:
        return customer

    if customer_id:
        found = Customer.objects.filter(tenant=tenant, pk=customer_id).first()
        if found:
            return found

    name = (customer_name or "").strip()
    if is_walk_in_name(name):
        return None

    found = Customer.objects.filter(tenant=tenant, name__iexact=name).first()
    if found:
        if phone and not found.phone:
            found.phone = str(phone).strip()[:20]
            found.save(update_fields=["phone"])
        return found

    if not create_if_missing or not name:
        return None

    return Customer.objects.create(
        tenant=tenant,
        name=name[:200],
        phone=(phone or "").strip()[:20],
        debt=Decimal("0"),
    )


@transaction.atomic
def apply_customer_debt_delta(customer: Customer | None, delta: Decimal | int | float | str) -> Decimal:
    """Qoldiqqa qo'shish (+) yoki kamaytirish (−). Manfiy qoldiqga tushirmaydi."""
    if customer is None:
        return Decimal("0")
    amount = Decimal(str(delta or 0))
    if amount == 0:
        return customer.debt

    locked = Customer.objects.select_for_update().get(pk=customer.pk)
    locked.debt = max(Decimal("0"), (locked.debt or Decimal("0")) + amount)
    locked.save(update_fields=["debt"])
    return locked.debt


def recalc_customer_debt(customer: Customer) -> Decimal:
    """Sotuv/qaytarishlardan qoldiqni qayta hisoblash."""
    sales_sum = (
        Sale.objects.filter(
            tenant=customer.tenant,
            customer=customer,
            status=Sale.STATUS_COMPLETED,
        ).aggregate(total=Sum("debt_amount"))["total"]
        or Decimal("0")
    )
    # Nom bilan bog'langan, lekin FK bo'sh qolgan eski sotuvlar
    name_sales = (
        Sale.objects.filter(
            tenant=customer.tenant,
            customer__isnull=True,
            customer_name__iexact=customer.name,
            status=Sale.STATUS_COMPLETED,
        ).aggregate(total=Sum("debt_amount"))["total"]
        or Decimal("0")
    )
    returns_sum = (
        SaleReturn.objects.filter(
            tenant=customer.tenant,
            customer=customer,
            status=SaleReturn.STATUS_COMPLETED,
        ).aggregate(total=Sum("debt_amount"))["total"]
        or Decimal("0")
    )
    name_returns = (
        SaleReturn.objects.filter(
            tenant=customer.tenant,
            customer__isnull=True,
            customer_name__iexact=customer.name,
            status=SaleReturn.STATUS_COMPLETED,
        ).aggregate(total=Sum("debt_amount"))["total"]
        or Decimal("0")
    )
    payments_sum = (
        CustomerDebtPayment.objects.filter(
            tenant=customer.tenant,
            customer=customer,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    balance = max(
        Decimal("0"),
        Decimal(str(sales_sum))
        + Decimal(str(name_sales))
        - Decimal(str(returns_sum))
        - Decimal(str(name_returns))
        - Decimal(str(payments_sum)),
    )
    if customer.debt != balance:
        customer.debt = balance
        customer.save(update_fields=["debt"])
    return balance
