from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import Product

from .models import Customer, Sale, SaleItem


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "phone", "debt"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].user.tenant
        return super().create(validated_data)


class SaleItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(write_only=True, required=False)

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
        ]
        read_only_fields = ["id", "product_name", "total"]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "client_id",
            "customer",
            "customer_name",
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
        ]
        read_only_fields = [
            "id",
            "receipt_number",
            "subtotal",
            "total",
            "created_at",
            "completed_at",
        ]

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        request = self.context["request"]
        tenant = request.user.tenant
        user = validated_data.pop("user", None) or request.user
        shift = validated_data.pop("shift", None)

        with transaction.atomic():
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
            for item_data in items_data:
                product = Product.objects.select_for_update().get(
                    id=item_data["product_id"], tenant=tenant
                )
                qty = Decimal(str(item_data["quantity"]))
                unit_price = Decimal(str(item_data.get("unit_price", product.price)))
                discount = Decimal(str(item_data.get("discount", 0)))
                line_total = qty * unit_price - discount

                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    product_name=product.name,
                    quantity=qty,
                    unit_price=unit_price,
                    discount=discount,
                    total=line_total,
                )
                subtotal += line_total

                if sale.status == Sale.STATUS_COMPLETED:
                    product.quantity = product.quantity - qty
                    product.save(update_fields=["quantity", "updated_at"])

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

        validated_data["client_id"] = client_id
        return SaleSerializer(context=self.context).create(validated_data)
