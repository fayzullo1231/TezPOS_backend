from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0011_product_min_stock"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["tenant", "is_active"],
                name="catalog_pro_tenant__is_act_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["tenant", "updated_at"],
                name="catalog_pro_tenant__upd_at_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["tenant", "category"],
                name="catalog_pro_tenant__categ_idx",
            ),
        ),
    ]
