from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0010_productimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="min_stock",
            field=models.DecimalField(
                decimal_places=3,
                default=0,
                help_text="Shu qiymatga yetganda kam qoldiq ogohlantiriladi",
                max_digits=14,
            ),
        ),
    ]
