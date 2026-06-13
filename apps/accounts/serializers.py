from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import CashTransaction, Employee, Shift, Tenant, User


class LoginSerializer(serializers.Serializer):
    server_name = serializers.CharField(max_length=100)
    login = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, write_only=True)

    def validate(self, attrs):
        server_name = attrs["server_name"].strip()
        login = attrs["login"].strip()

        try:
            tenant = Tenant.objects.get(server_name__iexact=server_name, is_active=True)
        except Tenant.DoesNotExist:
            raise serializers.ValidationError({"server_name": "Server topilmadi."})

        user = User.objects.filter(
            tenant=tenant, username__iexact=login, is_active=True
        ).first()
        if not user or not user.check_password(attrs["password"]):
            user = None

        if user is None:
            raise serializers.ValidationError({"login": "Login yoki parol noto'g'ri."})

        attrs["user"] = user
        attrs["tenant"] = tenant
        return attrs


class RegisterSerializer(serializers.Serializer):
    server_name = serializers.CharField(max_length=100)
    display_name = serializers.CharField(max_length=200)
    login = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=6, write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, default="")

    def validate_server_name(self, value):
        if Tenant.objects.filter(server_name__iexact=value.strip()).exists():
            raise serializers.ValidationError("Bu server nomi band.")
        return value.strip().lower()

    def create(self, validated_data):
        tenant = Tenant.objects.create(
            server_name=validated_data["server_name"],
            display_name=validated_data["display_name"],
        )
        user = User.objects.create_user(
            username=validated_data["login"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            tenant=tenant,
            role="super_admin",
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(read_only=True)
    server_name = serializers.CharField(source="tenant.server_name", read_only=True)
    display_name = serializers.CharField(source="tenant.display_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "role",
            "role_display",
            "api_token",
            "server_name",
            "display_name",
        ]
        read_only_fields = ["id", "api_token", "role_display", "server_name", "display_name"]


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ["id", "name", "phone", "salary_day", "salary_amount"]
        read_only_fields = ["id"]

    def validate_salary_day(self, value):
        if value < 1 or value > 31:
            raise serializers.ValidationError("Oylik kuni 1–31 oralig'ida bo'lishi kerak.")
        return value

    def validate_salary_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("Oylik summasi manfiy bo'lmasligi kerak.")
        return value

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].user.tenant
        return super().create(validated_data)


class StaffUserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    role_display = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "role",
            "role_display",
            "display_name",
            "is_active",
        ]

    def get_display_name(self, obj):
        name = f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return name or obj.username


class StaffCreateSerializer(serializers.Serializer):
    login = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=6, write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(
        choices=[("admin", "Admin"), ("manager", "Menejer"), ("cashier", "Kassir")],
        default="cashier",
    )

    def validate_login(self, value):
        login = value.strip()
        tenant = self.context["request"].user.tenant
        if User.objects.filter(tenant=tenant, username__iexact=login).exists():
            raise serializers.ValidationError("Bu login band.")
        return login

    def create(self, validated_data):
        tenant = self.context["request"].user.tenant
        return User.objects.create_user(
            username=validated_data["login"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            tenant=tenant,
            role=validated_data.get("role", "cashier"),
        )


class StaffUpdateSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=6, write_only=True, required=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    role = serializers.ChoiceField(
        choices=[("admin", "Admin"), ("manager", "Menejer"), ("cashier", "Kassir")],
        required=False,
    )
    is_active = serializers.BooleanField(required=False)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class TenantInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "server_name", "display_name", "is_active", "created_at"]
        read_only_fields = fields


class TenantCreateSerializer(serializers.Serializer):
    server_name = serializers.CharField(max_length=100)
    display_name = serializers.CharField(max_length=200)
    admin_login = serializers.CharField(max_length=150)
    admin_password = serializers.CharField(min_length=6, write_only=True)
    admin_first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")

    def validate_server_name(self, value):
        slug = value.strip().lower()
        if not slug.replace("-", "").replace("_", "").isalnum():
            raise serializers.ValidationError(
                "Server nomi faqat harf, raqam, - va _ dan iborat bo'lishi kerak."
            )
        if Tenant.objects.filter(server_name__iexact=slug).exists():
            raise serializers.ValidationError("Bu server nomi band.")
        return slug

    def create(self, validated_data):
        tenant = Tenant.objects.create(
            server_name=validated_data["server_name"],
            display_name=validated_data["display_name"].strip(),
        )
        User.objects.create_user(
            username=validated_data["admin_login"].strip(),
            password=validated_data["admin_password"],
            first_name=validated_data.get("admin_first_name", ""),
            tenant=tenant,
            role="super_admin",
        )
        return tenant


class CashTransactionCreateSerializer(serializers.Serializer):
    transaction_type = serializers.ChoiceField(choices=CashTransaction.TYPE_CHOICES)
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01")
    )
    category = serializers.CharField(max_length=120, required=False, allow_blank=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(
        choices=CashTransaction.PAYMENT_CHOICES, default=CashTransaction.PAYMENT_CASH
    )
    party_type = serializers.ChoiceField(
        choices=[
            ("client", "Mijoz"),
            ("supplier", "Yetkazib beruvchi"),
            ("employee", "Xodim"),
        ],
        required=False,
        allow_blank=True,
    )
    party_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    occurred_at = serializers.DateTimeField(required=False)

    def validate_occurred_at(self, value):
        if value is None:
            return timezone.now()
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def _resolve_category(self, tx_type, party_type, party_name, explicit):
        if explicit:
            return explicit.strip()
        if tx_type == CashTransaction.TYPE_TRANSFER:
            return "Pul o'tkazmasi"
        if party_type == "client":
            return "Mijozdan tushum" if tx_type == CashTransaction.TYPE_INCOME else "Mijozga chiqim"
        if party_type == "supplier":
            return (
                "Yetkazib beruvchidan tushum"
                if tx_type == CashTransaction.TYPE_INCOME
                else "Yetkazib beruvchiga chiqim"
            )
        defaults = {
            CashTransaction.TYPE_INCOME: "Kirim",
            CashTransaction.TYPE_EXPENSE: "Chiqim",
            CashTransaction.TYPE_TRANSFER: "Pul o'tkazmasi",
        }
        return defaults[tx_type]

    def create(self, validated_data):
        request = self.context["request"]
        tenant = request.user.tenant
        if not tenant:
            raise serializers.ValidationError(
                {"detail": "Server (tenant) topilmadi. Qayta kiring."}
            )
        tx_type = validated_data["transaction_type"]
        party_type = (validated_data.get("party_type") or "").strip()
        party_name = (validated_data.get("party_name") or "").strip()
        category = self._resolve_category(
            tx_type,
            party_type,
            party_name,
            validated_data.get("category") or "",
        )

        last = (
            CashTransaction.objects.filter(tenant=tenant)
            .order_by("-number")
            .values_list("number", flat=True)
            .first()
        )
        number = (last or 100000) + 1

        shift = (
            request.user.shifts.filter(status=Shift.STATUS_OPEN)
            .order_by("-opened_at")
            .first()
        )

        occurred_at = validated_data.get("occurred_at") or timezone.now()

        return CashTransaction.objects.create(
            tenant=tenant,
            user=request.user,
            shift=shift,
            number=number,
            transaction_type=tx_type,
            category=category,
            amount=validated_data["amount"],
            description=(validated_data.get("description") or "").strip(),
            payment_method=validated_data.get("payment_method") or CashTransaction.PAYMENT_CASH,
            party_type=party_type,
            party_name=party_name,
            occurred_at=occurred_at,
        )


class ShiftOpenSerializer(serializers.Serializer):
    opening_cash = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)
    opening_terminal = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)


class ShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = [
            "id",
            "opened_at",
            "closed_at",
            "status",
            "opening_cash",
            "opening_terminal",
        ]
        read_only_fields = ["id", "opened_at", "closed_at", "status"]
