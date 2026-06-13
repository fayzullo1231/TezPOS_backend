import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0007_mark_selling_price_list"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StockAudit",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("warehouse", models.CharField(default="Asosiy", max_length=120)),
                ("currency", models.CharField(default="SUM", max_length=10)),
                ("audit_number", models.PositiveIntegerField(db_index=True, default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[("completed", "Yakunlangan")],
                        default="completed",
                        max_length=20,
                    ),
                ),
                ("price_list_ids", models.JSONField(blank=True, default=list)),
                ("include_selling_price", models.BooleanField(default=False)),
                ("include_stock", models.BooleanField(default=True)),
                ("include_cost_price", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stock_audits",
                        to="accounts.tenant",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="stock_audits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Reviziya cheki",
                "verbose_name_plural": "Reviziya cheklari",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="StockAuditItem",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("product_name", models.CharField(max_length=300)),
                (
                    "quantity_before",
                    models.DecimalField(decimal_places=3, default=0, max_digits=14),
                ),
                (
                    "quantity_after",
                    models.DecimalField(
                        blank=True, decimal_places=3, max_digits=14, null=True
                    ),
                ),
                (
                    "cost_price",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=14, null=True
                    ),
                ),
                (
                    "sale_price",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=14, null=True
                    ),
                ),
                ("list_prices", models.JSONField(blank=True, default=dict)),
                (
                    "audit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="catalog.stockaudit",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stock_audit_items",
                        to="catalog.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "Reviziya qatori",
                "verbose_name_plural": "Reviziya qatorlari",
            },
        ),
    ]
