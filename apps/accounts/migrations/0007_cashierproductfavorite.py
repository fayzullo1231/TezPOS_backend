import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_employee"),
        ("catalog", "0004_unitofmeasure_product_unit_ref"),
    ]

    operations = [
        migrations.CreateModel(
            name="CashierProductFavorite",
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
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="cashier_favorites",
                        to="catalog.product",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="quick_add_favorites",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="cashierproductfavorite",
            constraint=models.UniqueConstraint(
                fields=("user", "product"), name="unique_user_quick_add_favorite"
            ),
        ),
    ]
