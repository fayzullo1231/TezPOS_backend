from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import CashTransaction, Shift, Tenant
from apps.catalog.models import Product, StockAudit, StockReceipt
from apps.sales.models import Customer, Sale, SaleReturn


class Command(BaseCommand):
    help = (
        "Mahsulotlarga tegmasdan sotuv, qaytarish, kirim, reviziya, kassa va smenalarni "
        "o'chiradi; mahsulot qoldig'ini 0 qiladi."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            type=str,
            help="Server nomi (masalan: demo, kuloloptom)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Barcha serverlar uchun reset",
        )

    def handle(self, *args, **options):
        if options["all"]:
            tenants = Tenant.objects.order_by("server_name")
        elif options["tenant"]:
            name = options["tenant"].strip().lower()
            tenants = Tenant.objects.filter(server_name__iexact=name)
            if not tenants.exists():
                raise CommandError(f"Server topilmadi: {options['tenant']}")
        else:
            raise CommandError("--tenant <nom> yoki --all ko'rsating.")

        for tenant in tenants:
            self._reset_tenant(tenant)

    @transaction.atomic
    def _reset_tenant(self, tenant: Tenant):
        sales = Sale.objects.filter(tenant=tenant).count()
        returns = SaleReturn.objects.filter(tenant=tenant).count()
        receipts = StockReceipt.objects.filter(tenant=tenant).count()
        audits = StockAudit.objects.filter(tenant=tenant).count()
        cash = CashTransaction.objects.filter(tenant=tenant).count()
        shifts = Shift.objects.filter(tenant=tenant).count()
        products = Product.objects.filter(tenant=tenant).count()

        Sale.objects.filter(tenant=tenant).delete()
        SaleReturn.objects.filter(tenant=tenant).delete()
        StockReceipt.objects.filter(tenant=tenant).delete()
        StockAudit.objects.filter(tenant=tenant).delete()
        CashTransaction.objects.filter(tenant=tenant).delete()
        Shift.objects.filter(tenant=tenant).delete()

        zeroed = Product.objects.filter(tenant=tenant).update(quantity=Decimal("0"))
        debts = Customer.objects.filter(tenant=tenant).update(debt=Decimal("0"))

        self.stdout.write(
            self.style.SUCCESS(
                f"{tenant.server_name}: o'chirildi — "
                f"sotuv={sales}, qaytarish={returns}, kirim={receipts}, "
                f"reviziya={audits}, kassa={cash}, smena={shifts}; "
                f"qoldiq 0: {zeroed}/{products} mahsulot, qarz 0: {debts} mijoz"
            )
        )
