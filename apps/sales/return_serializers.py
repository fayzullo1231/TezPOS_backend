from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import Product

from .models import SaleReturn, SaleReturnItem


class SaleReturnItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = SaleReturnItem
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


class SaleReturnSerializer(serializers.ModelSerializer):
    items = SaleReturnItemSerializer(many=True)

    class Meta:
        model = SaleReturn
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
                SaleReturn.objects.filter(tenant=tenant)
                .order_by("-receipt_number")
                .values_list("receipt_number", flat=True)
                .first()
            )
            receipt_number = (last or 0) + 1

            sale_return = SaleReturn.objects.create(
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

                SaleReturnItem.objects.create(
                    sale_return=sale_return,
                    product=product,
                    product_name=product.name,
                    quantity=qty,
                    unit_price=unit_price,
                    discount=discount,
                    total=line_total,
                )
                subtotal += line_total

                if sale_return.status == SaleReturn.STATUS_COMPLETED:
                    product.quantity = product.quantity + qty
                    product.save(update_fields=["quantity", "updated_at"])

            sale_return.subtotal = subtotal
            sale_return.discount_amount = validated_data.get(
                "discount_amount", Decimal("0")
            )
            sale_return.total = subtotal - sale_return.discount_amount
            paid = validated_data.get("paid_amount")
            if paid is not None:
                sale_return.paid_amount = Decimal(str(paid))
                sale_return.debt_amount = max(
                    Decimal("0"), sale_return.total - sale_return.paid_amount
                )
            elif sale_return.payment_type == SaleReturn.PAYMENT_CREDIT:
                sale_return.paid_amount = Decimal("0")
                sale_return.debt_amount = sale_return.total
            else:
                sale_return.paid_amount = sale_return.total
                sale_return.debt_amount = Decimal("0")
            if sale_return.status == SaleReturn.STATUS_COMPLETED:
                sale_return.completed_at = timezone.now()
                sale_return.synced_at = timezone.now()
            sale_return.save()

        return sale_return


class SaleReturnListSerializer(serializers.ModelSerializer):
    items_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = SaleReturn
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
