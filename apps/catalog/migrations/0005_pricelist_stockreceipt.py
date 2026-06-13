import uuid

from django.db import migrations, models
import django.db.models.deletion


def seed_price_lists(apps, schema_editor):
    Tenant = apps.get_model("accounts", "Tenant")
    PriceList = apps.get_model("catalog", "PriceList")
    for tenant in Tenant.objects.all():
        if PriceList.objects.filter(tenant=tenant).exists():
            continue
        PriceList.objects.create(
            tenant=tenant,
            name="optom",
            sort_order=0,
            is_selling=False,
        )
        PriceList.objects.create(
            tenant=tenant,
            name="chakana",
            sort_order=1,
            is_selling=False,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_remove_cashierproductfavorite"),
        ("catalog", "0004_unitofmeasure_product_unit_ref"),
    ]

    operations = [
        migrations.CreateModel(
            name="PriceList",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("is_selling", models.BooleanField(default=False)),
                ("sort_order", models.IntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_lists",
                        to="accounts.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Narxlar ro'yxati",
                "verbose_name_plural": "Narxlar ro'yxatlari",
                "ordering": ["sort_order", "name"],
                "unique_together": {("tenant", "name")},
            },
        ),
        migrations.CreateModel(
            name="StockReceipt",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("supplier_name", models.CharField(blank=True, max_length=200)),
                ("warehouse", models.CharField(default="Asosiy", max_length=120)),
                ("currency", models.CharField(default="SUM", max_length=10)),
                ("receipt_number", models.PositiveIntegerField(db_index=True, default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Qoralama"), ("completed", "Yakunlangan")],
                        default="completed",
                        max_length=20,
                    ),
                ),
                ("price_list_ids", models.JSONField(blank=True, default=list)),
                ("include_selling_price", models.BooleanField(default=True)),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "supplier",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="stock_receipts",
                        to="catalog.supplier",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stock_receipts",
                        to="accounts.tenant",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="stock_receipts",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "verbose_name": "Kirim cheki",
                "verbose_name_plural": "Kirim cheklari",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ProductPrice",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "price",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                (
                    "price_list",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="product_prices",
                        to="catalog.pricelist",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="list_prices",
                        to="catalog.product",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="product_prices",
                        to="accounts.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Mahsulot narxi",
                "verbose_name_plural": "Mahsulot narxlari",
                "unique_together": {("product", "price_list")},
            },
        ),
        migrations.CreateModel(
            name="StockReceiptItem",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("product_name", models.CharField(max_length=300)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=14)),
                (
                    "cost_price",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                (
                    "sale_price",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                ("list_prices", models.JSONField(blank=True, default=dict)),
                (
                    "line_total",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stock_receipt_items",
                        to="catalog.product",
                    ),
                ),
                (
                    "receipt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="catalog.stockreceipt",
                    ),
                ),
            ],
            options={
                "verbose_name": "Kirim qatori",
                "verbose_name_plural": "Kirim qatorlari",
            },
        ),
        migrations.RunPython(seed_price_lists, migrations.RunPython.noop),
    ]
