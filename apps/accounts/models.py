import secrets
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Tenant(models.Model):
    """Har bir biznes (server) — alohida ma'lumotlar bazasi maydoni."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    server_name = models.CharField(max_length=100, unique=True, db_index=True)
    display_name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Server"
        verbose_name_plural = "Serverlar"

    def __str__(self):
        return self.server_name


class User(AbstractUser):
    ROLE_CHOICES = [
        ("super_admin", "Super-Admin"),
        ("admin", "Admin"),
        ("cashier", "Kassir"),
        ("manager", "Menejer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="users", null=True, blank=True
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="cashier")
    api_token = models.CharField(max_length=64, unique=True, blank=True, db_index=True)
    phone = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "username"], name="unique_tenant_username"
            )
        ]

    def save(self, *args, **kwargs):
        if not self.api_token:
            self.api_token = secrets.token_hex(32)
        super().save(*args, **kwargs)

    @property
    def role_display(self):
        return dict(self.ROLE_CHOICES).get(self.role, self.role)


class Employee(models.Model):
    """Biznes xodimi — maosh va kassa chiqimlari uchun."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="employees")
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    salary_day = models.PositiveSmallIntegerField(default=1)
    salary_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Xodim"
        verbose_name_plural = "Xodimlar"

    def __str__(self):
        return self.name


class Shift(models.Model):
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Ochiq"),
        (STATUS_CLOSED, "Yopilgan"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="shifts")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="shifts")
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    opening_cash = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    opening_terminal = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["-opened_at"]


class CashTransaction(models.Model):
    """Kassa kirim / chiqim / o'tkazma."""

    TYPE_INCOME = "income"
    TYPE_EXPENSE = "expense"
    TYPE_TRANSFER = "transfer"
    TYPE_CHOICES = [
        (TYPE_INCOME, "Kirim"),
        (TYPE_EXPENSE, "Chiqim"),
        (TYPE_TRANSFER, "Pul o'tkazmasi"),
    ]

    PAYMENT_CASH = "cash"
    PAYMENT_CARD = "card"
    PAYMENT_CHOICES = [
        (PAYMENT_CASH, "Naqd"),
        (PAYMENT_CARD, "Terminal"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="cash_transactions")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="cash_transactions")
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True)
    number = models.PositiveIntegerField(default=0, db_index=True)
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_CHOICES, default=PAYMENT_CASH
    )
    category = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=500, blank=True)
    party_type = models.CharField(max_length=20, blank=True)
    party_name = models.CharField(max_length=200, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Kassa tranzaksiyasi"
        verbose_name_plural = "Kassa tranzaksiyalari"
