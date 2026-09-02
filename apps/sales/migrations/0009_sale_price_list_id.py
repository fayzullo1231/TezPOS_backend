from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0008_fifo_stock_batches"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="price_list_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Bo'sh = Sotuv narxi; UUID = optom/boshqa ro'yxat",
                max_length=64,
            ),
        ),
    ]
