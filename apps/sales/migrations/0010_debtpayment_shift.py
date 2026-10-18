from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_shift_close_and_defaults"),
        ("sales", "0009_sale_price_list_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="customerdebtpayment",
            name="client_id",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="customerdebtpayment",
            name="shift",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="debt_payments",
                to="accounts.shift",
            ),
        ),
    ]
