from django.core.management.base import BaseCommand

from apps.accounts.models import Tenant
from apps.sales.debt_utils import recalc_customer_debt
from apps.sales.models import Customer, Sale


class Command(BaseCommand):
    help = "Mijoz qarz qoldiqlarini sotuv/qaytarishlardan qayta hisoblash"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=str, default="", help="server_name (ixtiyoriy)")

    def handle(self, *args, **options):
        slug = (options.get("tenant") or "").strip()
        tenants = Tenant.objects.all()
        if slug:
            tenants = tenants.filter(server_name__iexact=slug)

        total = 0
        for tenant in tenants:
            # FK yo'q, lekin qarzli sotuvlari bor mijozlarni yaratib bog'lash
            orphan_names = (
                Sale.objects.filter(
                    tenant=tenant,
                    status=Sale.STATUS_COMPLETED,
                    customer__isnull=True,
                    debt_amount__gt=0,
                )
                .exclude(customer_name="")
                .values_list("customer_name", flat=True)
                .distinct()
            )
            for name in orphan_names:
                name = (name or "").strip()
                if not name:
                    continue
                cust, _ = Customer.objects.get_or_create(
                    tenant=tenant,
                    name=name,
                    defaults={"phone": "", "debt": 0},
                )
                Sale.objects.filter(
                    tenant=tenant,
                    customer__isnull=True,
                    customer_name__iexact=name,
                ).update(customer=cust)

            for customer in Customer.objects.filter(tenant=tenant):
                before = customer.debt
                after = recalc_customer_debt(customer)
                if before != after:
                    self.stdout.write(
                        f"{tenant.server_name} / {customer.name}: {before} → {after}"
                    )
                total += 1

        self.stdout.write(self.style.SUCCESS(f"Tayyor. {total} mijoz tekshirildi."))
