from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0014_backfill_opening_batches"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockreceipt",
            name="payment_type",
            field=models.CharField(
                choices=[("cash", "Naqd"), ("credit", "Qarzga")],
                db_index=True,
                default="cash",
                max_length=20,
            ),
        ),
    ]
