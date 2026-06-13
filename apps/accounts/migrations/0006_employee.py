import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_cashtransaction_occurred_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="Employee",
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
                ("name", models.CharField(max_length=200)),
                ("phone", models.CharField(blank=True, max_length=20)),
                ("salary_day", models.PositiveSmallIntegerField(default=1)),
                (
                    "salary_amount",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="employees",
                        to="accounts.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Xodim",
                "verbose_name_plural": "Xodimlar",
                "ordering": ["name"],
            },
        ),
    ]
