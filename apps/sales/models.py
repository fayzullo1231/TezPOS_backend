import uuid

from django.db import models

from apps.accounts.models import Shift, Tenant, User
from apps.catalog.models import Product


class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    debt = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CustomerDebtPayment(models.Model):
    """Qarzning bir qismini (yoki to'liq) to'lash."""

    PAYMENT_CASH = "cash"
    PAYMENT_CARD = "card"
    PAYMENT_CHOICES = [
        (PAYMENT_CASH, "Naqd"),
        (PAYMENT_CARD, "Terminal"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="debt_payments"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="debt_payments"
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="debt_payments"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_type = models.CharField(
        max_length=20, choices=PAYMENT_CHOICES, default=PAYMENT_CASH
    )
    note = models.CharField(max_length=255, blank=True)
    receipt_number = models.PositiveIntegerField(default=0)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Qarz to'lovi"
        verbose_name_plural = "Qarz to'lovlari"

    def __str__(self):
        return f"#{self.receipt_number} — {self.amount}"


class Sale(models.Model):
    """Sotuv / buyurtma."""

    STATUS_DRAFT = "draft"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Qoralama"),
        (STATUS_COMPLETED, "Yakunlangan"),
        (STATUS_CANCELLED, "Bekor qilingan"),
    ]

    PAYMENT_CASH = "cash"
    PAYMENT_CARD = "card"
    PAYMENT_MIXED = "mixed"
    PAYMENT_CREDIT = "credit"
    PAYMENT_CHOICES = [
        (PAYMENT_CASH, "Naqd"),
        (PAYMENT_CARD, "Karta"),
        (PAYMENT_MIXED, "Aralash"),
        (PAYMENT_CREDIT, "Qarzga"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_id = models.CharField(max_length=64, blank=True, db_index=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="sales")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="sales")
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True)
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True
    )
    customer_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    payment_type = models.CharField(
        max_length=20, choices=PAYMENT_CHOICES, default=PAYMENT_CASH
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    debt_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    comment = models.TextField(blank=True)
    receipt_number = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Buyurtma"
        verbose_name_plural = "Buyurtmalar"

    def __str__(self):
        return f"#{self.receipt_number} — {self.total}"


class SaleItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sale_items")
    product_name = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]


class SaleReturn(models.Model):
    """Qaytarish — buyurtmalardan alohida."""

    STATUS_DRAFT = "draft"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Qoralama"),
        (STATUS_COMPLETED, "Yakunlangan"),
        (STATUS_CANCELLED, "Bekor qilingan"),
    ]

    PAYMENT_CASH = "cash"
    PAYMENT_CARD = "card"
    PAYMENT_MIXED = "mixed"
    PAYMENT_CREDIT = "credit"
    PAYMENT_CHOICES = [
        (PAYMENT_CASH, "Naqd"),
        (PAYMENT_CARD, "Karta"),
        (PAYMENT_MIXED, "Aralash"),
        (PAYMENT_CREDIT, "Qarzga"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_id = models.CharField(max_length=64, blank=True, db_index=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="returns")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="returns")
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True)
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="returns"
    )
    customer_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    payment_type = models.CharField(
        max_length=20, choices=PAYMENT_CHOICES, default=PAYMENT_CASH
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    debt_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    comment = models.TextField(blank=True)
    receipt_number = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Qaytarish"
        verbose_name_plural = "Qaytarishlar"

    def __str__(self):
        return f"Qaytarish #{self.receipt_number} — {self.total}"


class SaleReturnItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale_return = models.ForeignKey(
        SaleReturn, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="return_items"
    )
    product_name = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Qaytarish mahsuloti"
        verbose_name_plural = "Qaytarish mahsulotlari"
