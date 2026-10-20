from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0015_stockreceipt_payment_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stockreceipt",
            name="payment_type",
            field=models.CharField(
                choices=[("cash", "Naqd"), ("credit", "Qarzga"), ("bonus", "Bonus")],
                db_index=True,
                default="cash",
                max_length=20,
            ),
        ),
    ]
