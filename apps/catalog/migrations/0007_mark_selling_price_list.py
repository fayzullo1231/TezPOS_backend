from django.db import migrations


def _is_selling_name(name: str) -> bool:
    lower = name.lower()
    return (
        "продаж" in lower
        or "sotuv" in lower
        or "sotish" in lower
        or "розниц" in lower
    )


def mark_selling_price_lists(apps, schema_editor):
    Tenant = apps.get_model("accounts", "Tenant")
    PriceList = apps.get_model("catalog", "PriceList")

    for tenant in Tenant.objects.all():
        lists = list(
            PriceList.objects.filter(tenant=tenant, is_active=True).order_by(
                "sort_order", "name"
            )
        )
        if not lists:
            continue

        selling = next((pl for pl in lists if pl.is_selling), None)
        if not selling:
            selling = next((pl for pl in lists if _is_selling_name(pl.name)), None)

        if not selling:
            continue

        PriceList.objects.filter(tenant=tenant, is_selling=True).exclude(
            pk=selling.pk
        ).update(is_selling=False)

        if not selling.is_selling:
            selling.is_selling = True
            selling.save(update_fields=["is_selling"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0006_brand_product_brand"),
    ]

    operations = [
        migrations.RunPython(mark_selling_price_lists, migrations.RunPython.noop),
    ]
