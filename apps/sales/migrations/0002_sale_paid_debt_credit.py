from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="paid_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="sale",
            name="debt_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AlterField(
            model_name="sale",
            name="payment_type",
            field=models.CharField(
                choices=[
                    ("cash", "Naqd"),
                    ("card", "Karta"),
                    ("mixed", "Aralash"),
                    ("credit", "Qarzga"),
                ],
                default="cash",
                max_length=20,
            ),
        ),
    ]
