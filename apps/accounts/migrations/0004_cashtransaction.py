import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_alter_user_groups_alter_user_is_active_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CashTransaction",
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
                ("number", models.PositiveIntegerField(db_index=True, default=0)),
                (
                    "transaction_type",
                    models.CharField(
                        choices=[
                            ("income", "Kirim"),
                            ("expense", "Chiqim"),
                            ("transfer", "Pul o'tkazmasi"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "payment_method",
                    models.CharField(
                        choices=[("cash", "Naqd"), ("card", "Terminal")],
                        default="cash",
                        max_length=20,
                    ),
                ),
                ("category", models.CharField(max_length=120)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("description", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "shift",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="accounts.shift",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cash_transactions",
                        to="accounts.tenant",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cash_transactions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Kassa tranzaksiyasi",
                "verbose_name_plural": "Kassa tranzaksiyalari",
                "ordering": ["-created_at"],
            },
        ),
    ]
