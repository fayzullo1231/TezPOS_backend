from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.catalog.fifo import InsufficientStockError, consume_fifo, stock_snapshot
from apps.catalog.models import Product

from .debt_utils import resolve_customer
from .models import Customer, Sale, SaleItem, SaleItemBatch


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "phone", "debt"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].user.tenant
        validated_data.setdefault("debt", Decimal("0"))
        return super().create(validated_data)


class SaleItemBatchSerializer(serializers.ModelSerializer):
    batch_number = serializers.IntegerField(source="batch.batch_number", read_only=True)

    class Meta:
        model = SaleItemBatch
        fields = ["id", "batch", "batch_number", "quantity", "unit_cost"]


class SaleItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(required=False)
    sort_order = serializers.IntegerField(required=False, default=0)
    batch_allocations = SaleItemBatchSerializer(many=True, read_only=True)

    class Meta:
        model = SaleItem
        fields = [
            "id",
            "product_id",
            "product_name",
            "quantity",
            "unit_price",
            "discount",
            "total",
            "sort_order",
            "batch_allocations",
        ]
        read_only_fields = ["id", "product_name", "total", "batch_allocations"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Client savatga qaytarish / chek tartibi uchun
        pid = getattr(instance, "product_id", None)
        data["product_id"] = str(pid) if pid else None
        data["sort_order"] = int(getattr(instance, "sort_order", 0) or 0)
        return data


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)
    customer_id = serializers.UUIDField(
        write_only=True, required=False, allow_null=True
    )
    customer_debt_before = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        write_only=True,
        required=False,
        allow_null=True,
        min_value=Decimal("0"),
    )
    customer_debt = serializers.SerializerMethodField(read_only=True)
    customer_debt_balance = serializers.SerializerMethodField(read_only=True)
    customer_phone = serializers.SerializerMethodField(read_only=True)
    stock_updates = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "client_id",
            "customer",
            "customer_id",
            "customer_debt_before",
            "customer_name",
            "customer_debt",
            "customer_debt_balance",
            "customer_phone",
            "status",
            "payment_type",
            "subtotal",
            "discount_amount",
            "total",
            "paid_amount",
            "debt_amount",
            "comment",
            "receipt_number",
            "items",
            "created_at",
            "completed_at",
            "stock_updates",
        ]
        read_only_fields = [
            "id",
            "receipt_number",
            "subtotal",
            "total",
            "created_at",
            "completed_at",
            "customer_debt",
            "customer_debt_balance",
            "customer_phone",
            "stock_updates",
        ]

    def get_customer_debt(self, obj):
        if obj.customer_id and obj.customer:
            return str(obj.customer.debt)
        return None

    def get_customer_debt_balance(self, obj):
        return self.get_customer_debt(obj)

    def get_customer_phone(self, obj):
        if obj.customer_id and obj.customer:
            return obj.customer.phone or ""
        return ""

    def get_stock_updates(self, obj):
        return getattr(obj, "_stock_updates", [])

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        customer_id = validated_data.pop("customer_id", None)
        customer_debt_before = validated_data.pop("customer_debt_before", None)
        request = self.context["request"]
        tenant = request.user.tenant
        user = validated_data.pop("user", None) or request.user
        shift = validated_data.pop("shift", None)

        customer_name = validated_data.get("customer_name", "")

        with transaction.atomic():
            customer = resolve_customer(
                tenant,
                customer=validated_data.get("customer"),
                customer_id=customer_id,
                customer_name=customer_name,
                create_if_missing=False,
            )
            if (
                customer is None
                and validated_data.get("payment_type") == Sale.PAYMENT_CREDIT
            ):
                name = (customer_name or "").strip()
                if not name:
                    raise serializers.ValidationError(
                        {"customer_id": "Qarzga sotish uchun mijozni tanlang."}
                    )
                customer = resolve_customer(
                    tenant,
                    customer_name=name,
                    create_if_missing=True,
                )
            if customer:
                validated_data["customer"] = customer
                if not (validated_data.get("customer_name") or "").strip():
                    validated_data["customer_name"] = customer.name

            last = (
                Sale.objects.filter(tenant=tenant)
                .order_by("-receipt_number")
                .values_list("receipt_number", flat=True)
                .first()
            )
            receipt_number = (last or 0) + 1

            sale = Sale.objects.create(
                tenant=tenant,
                user=user,
                shift=shift,
                receipt_number=receipt_number,
                **validated_data,
            )

            subtotal = Decimal("0")
            touched_pids = []
            for idx, item_data in enumerate(items_data):
                pid = item_data.get("product_id")
                product = None
                if pid:
                    try:
                        product = Product.objects.select_for_update().get(
                            id=pid, tenant=tenant
                        )
                    except Product.DoesNotExist:
                        product = None

                qty = Decimal(str(item_data["quantity"]))
                fallback_price = Decimal(str(item_data.get("price") or item_data.get("unit_price") or 0))
                unit_price = Decimal(str(item_data.get("unit_price", product.price if product else fallback_price)))
                discount = Decimal(str(item_data.get("discount", 0)))
                line_total = qty * unit_price - discount
                sort_order = item_data.get("sort_order")
                if sort_order is None:
                    sort_order = idx

                product_name = (product.name if product else None) or item_data.get("product_name") or "Noma'lum mahsulot"
                sale_item = SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    product_name=product_name,
                    quantity=qty,
                    unit_price=unit_price,
                    discount=discount,
                    total=line_total,
                    sort_order=int(sort_order),
                )
                subtotal += line_total

                if product and sale.status == Sale.STATUS_COMPLETED:
                    try:
                        consume_fifo(
                            product,
                            qty,
                            sale_item=sale_item,
                            reference_type="sale",
                            reference_id=sale.id,
                        )
                    except InsufficientStockError as exc:
                        raise exc.as_validation_error() from exc
                    touched_pids.append(pid)

            sale.subtotal = subtotal
            sale.discount_amount = validated_data.get("discount_amount", Decimal("0"))
            sale.total = subtotal - sale.discount_amount
            paid = validated_data.get("paid_amount")
            if paid is not None:
                sale.paid_amount = Decimal(str(paid))
                sale.debt_amount = max(Decimal("0"), sale.total - sale.paid_amount)
            elif sale.payment_type == Sale.PAYMENT_CREDIT:
                sale.paid_amount = Decimal("0")
                sale.debt_amount = sale.total
            else:
                sale.paid_amount = sale.total
                sale.debt_amount = Decimal("0")
            if sale.status == Sale.STATUS_COMPLETED:
                sale.completed_at = timezone.now()
                sale.synced_at = timezone.now()
            sale.save()

            # Qarz qoldig'iga qo'shish (yana sotilsa yig'ilib boradi)
            if (
                sale.status == Sale.STATUS_COMPLETED
                and sale.debt_amount
                and sale.debt_amount > 0
            ):
                if not sale.customer_id:
                    customer = resolve_customer(
                        tenant,
                        customer_name=sale.customer_name,
                        create_if_missing=True,
                    )
                    if customer:
                        sale.customer = customer
                        sale.save(update_fields=["customer"])
                if sale.customer_id:
                    locked = Customer.objects.select_for_update().get(
                        pk=sale.customer_id
                    )
                    saved_debt = locked.debt or Decimal("0")
                    # Eski desktop versiyalar qarzni faqat localStorage'da saqlagan
                    if (
                        customer_debt_before is not None
                        and Decimal(str(customer_debt_before)) > saved_debt
                    ):
                        saved_debt = Decimal(str(customer_debt_before))
                    locked.debt = saved_debt + sale.debt_amount
                    locked.save(update_fields=["debt"])
                    sale.customer = locked

            if sale.status == Sale.STATUS_COMPLETED:
                products = Product.objects.filter(tenant=tenant, id__in=touched_pids)
                sale._stock_updates = stock_snapshot(products)

        return sale


class SaleListSerializer(serializers.ModelSerializer):
    items_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "receipt_number",
            "customer_name",
            "subtotal",
            "discount_amount",
            "total",
            "paid_amount",
            "debt_amount",
            "status",
            "payment_type",
            "comment",
            "items_count",
            "synced_at",
            "created_at",
            "completed_at",
        ]


class SyncSaleSerializer(serializers.Serializer):
    client_id = serializers.CharField(max_length=64)
    customer_name = serializers.CharField(required=False, allow_blank=True, default="")
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    customer_debt_before = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal("0"),
    )
    payment_type = serializers.ChoiceField(choices=Sale.PAYMENT_CHOICES, default="cash")
    paid_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True
    )
    debt_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True
    )
    discount_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=Sale.STATUS_CHOICES, default="completed")
    created_at = serializers.DateTimeField(required=False)
    items = SaleItemSerializer(many=True)

    def create(self, validated_data):
        request = self.context["request"]
        client_id = validated_data["client_id"]

        existing = Sale.objects.filter(
            tenant=request.user.tenant, client_id=client_id
        ).first()
        if existing:
            return existing

        created_at = validated_data.pop("created_at", None)
        shift = (
            request.user.shifts.filter(status="open").order_by("-opened_at").first()
        )
        payload = {**validated_data, "client_id": client_id}
        if shift:
            payload["shift"] = shift

        sale = SaleSerializer(context=self.context).create(payload)
        if created_at:
            sale.completed_at = created_at
            sale.save(update_fields=["completed_at"])
        return sale
