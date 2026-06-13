from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_cashierproductfavorite"),
    ]

    operations = [
        migrations.DeleteModel(
            name="CashierProductFavorite",
        ),
    ]
