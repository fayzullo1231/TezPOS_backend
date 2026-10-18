from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_remove_cashierproductfavorite"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="default_opening_cash",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="tenant",
            name="default_opening_terminal",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="shift",
            name="closing_cash",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True
            ),
        ),
        migrations.AddField(
            model_name="shift",
            name="closing_terminal",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True
            ),
        ),
        migrations.AddField(
            model_name="shift",
            name="variance_cash",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True
            ),
        ),
        migrations.AddField(
            model_name="shift",
            name="variance_terminal",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True
            ),
        ),
        migrations.AddField(
            model_name="shift",
            name="variance_reason",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="shift",
            name="closed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="closed_shifts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="cashtransaction",
            name="client_id",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
    ]
