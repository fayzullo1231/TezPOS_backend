from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Django admin panel uchun admin/demo foydalanuvchilarga to'liq ruxsat beradi"

    def handle(self, *args, **options):
        updated = 0
        for username in ("admin", "demo"):
            user = User.objects.filter(username=username).first()
            if not user:
                continue
            changed = False
            if not user.is_staff:
                user.is_staff = True
                changed = True
            if not user.is_superuser:
                user.is_superuser = True
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if changed:
                user.save(update_fields=["is_staff", "is_superuser", "is_active"])
                updated += 1
                self.stdout.write(
                    self.style.SUCCESS(f"{username}: is_staff + is_superuser yoqildi")
                )
            else:
                self.stdout.write(f"{username}: allaqachon to'liq ruxsatli")

        if updated == 0 and not User.objects.filter(is_superuser=True).exists():
            self.stdout.write(
                self.style.WARNING(
                    "Superuser topilmadi. Yangi superuser: "
                    "python manage.py createsuperuser"
                )
            )
