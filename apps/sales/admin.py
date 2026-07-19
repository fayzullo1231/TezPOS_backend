from django.contrib import admin

from .models import (
    Customer,
    CustomerDebtPayment,
    Sale,
    SaleItem,
    SaleReturn,
    SaleReturnItem,
)


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


class SaleReturnItemInline(admin.TabularInline):
    model = SaleReturnItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ["receipt_number", "tenant", "total", "status", "created_at"]
    inlines = [SaleItemInline]


@admin.register(SaleReturn)
class SaleReturnAdmin(admin.ModelAdmin):
    list_display = ["receipt_number", "tenant", "total", "status", "created_at"]
    inlines = [SaleReturnItemInline]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "phone", "debt"]


@admin.register(CustomerDebtPayment)
class CustomerDebtPaymentAdmin(admin.ModelAdmin):
    list_display = [
        "receipt_number",
        "customer",
        "amount",
        "balance_after",
        "payment_type",
        "created_at",
    ]
    list_filter = ["payment_type"]
