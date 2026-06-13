import uuid

import django.db.models.deletion
from django.db import migrations, models


def copy_barcodes(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductBarcode = apps.get_model("catalog", "ProductBarcode")
    for product in Product.objects.exclude(barcode="").exclude(barcode__isnull=True):
        code = (product.barcode or "").strip()
        if not code:
            continue
        ProductBarcode.objects.get_or_create(
            tenant_id=product.tenant_id,
            code=code,
            defaults={"product_id": product.id},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductBarcode",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("code", models.CharField(db_index=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="barcodes",
                        to="catalog.product",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="product_barcodes",
                        to="accounts.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="productbarcode",
            index=models.Index(fields=["tenant", "code"], name="catalog_pro_tenant__bc_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="productbarcode",
            unique_together={("tenant", "code")},
        ),
        migrations.RunPython(copy_barcodes, migrations.RunPython.noop),
    ]
