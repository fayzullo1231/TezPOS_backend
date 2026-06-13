from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0002_sale_paid_debt_credit"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="is_return",
            field=models.BooleanField(default=False),
        ),
    ]
