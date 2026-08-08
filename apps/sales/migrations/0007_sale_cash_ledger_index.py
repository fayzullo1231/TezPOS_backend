from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0006_saleitem_sort_order"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="sale",
            index=models.Index(
                fields=["tenant", "status", "completed_at"],
                name="sales_sale_tenant_status_comp_idx",
            ),
        ),
    ]
