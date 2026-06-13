from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.accounts.models import Tenant, User
from apps.catalog.models import Category, Product, UnitOfMeasure


class Command(BaseCommand):
    help = "Demo server va mahsulotlarni yaratadi"

    def handle(self, *args, **options):
        demo_tenant, _ = Tenant.objects.get_or_create(
            server_name="demo",
            defaults={"display_name": "Demo Do'kon"},
        )
        kulol_tenant, _ = Tenant.objects.get_or_create(
            server_name="kuloloptom",
            defaults={"display_name": "Kulol Optom"},
        )

        # kuloloptom: admin (global username — mavjud bo'lsa tenantga bog'laymiz)
        admin = User.objects.filter(username="admin").first()
        if admin:
            admin.tenant = kulol_tenant
            admin.is_active = True
            admin.role = "super_admin"
            admin.is_staff = True
            admin.set_password("admin123")
            admin.save()
            self.stdout.write("kuloloptom: admin / admin123 (yangilandi)")
        else:
            User.objects.create_user(
                username="admin",
                password="admin123",
                first_name="Admin",
                tenant=kulol_tenant,
                role="super_admin",
                is_staff=True,
            )
            self.stdout.write(self.style.SUCCESS("kuloloptom: admin / admin123 (yangi)"))

        # demo: alohida login (username global unique)
        demo_user = User.objects.filter(username="demo").first()
        if demo_user:
            demo_user.tenant = demo_tenant
            demo_user.is_active = True
            demo_user.role = "super_admin"
            demo_user.is_staff = True
            demo_user.set_password("demo123")
            demo_user.save()
            self.stdout.write("demo: demo / demo123 (yangilandi)")
        else:
            User.objects.create_user(
                username="demo",
                password="demo123",
                first_name="Demo",
                tenant=demo_tenant,
                role="super_admin",
                is_staff=True,
            )
            self.stdout.write(self.style.SUCCESS("demo: demo / demo123 (yangi)"))

        cat, _ = Category.objects.get_or_create(
            tenant=demo_tenant, name="Ichimliklar", defaults={"sort_order": 1}
        )
        products = [
            ("Coca-Cola 0.5L", "8600000000001", "8000"),
            ("Coca-Cola 1L", "8600000000002", "12000"),
            ("Fanta 0.5L", "8600000000003", "7500"),
            ("Pepsi 0.5L", "8600000000004", "7500"),
            ("Suv 0.5L", "8600000000005", "3000"),
            ("Non", "8600000000010", "4000"),
            ("Sut 1L", "8600000000011", "14000"),
            ("Tuxum (10 dona)", "8600000000012", "18000"),
        ]
        for name, barcode, price in products:
            Product.objects.update_or_create(
                tenant=demo_tenant,
                barcode=barcode,
                defaults={
                    "name": name,
                    "price": Decimal(price),
                    "quantity": Decimal("100"),
                    "category": cat,
                },
            )

        default_units = [
            ("dona", False),
            ("шт", False),
            ("kg", True),
            ("кг", True),
            ("g", True),
            ("gr", True),
            ("litr", False),
            ("l", False),
        ]
        for uname, weighable in default_units:
            UnitOfMeasure.objects.get_or_create(
                tenant=demo_tenant,
                name=uname,
                defaults={"is_weighable": weighable},
            )

        self.stdout.write(self.style.SUCCESS("Tayyor."))
