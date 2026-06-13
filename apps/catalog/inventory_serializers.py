from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (
    PriceList,
    Product,
    ProductPrice,
    StockAudit,
    StockAuditItem,
    StockReceipt,
    StockReceiptItem,
)


class PriceListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceList
        fields = ["id", "name", "is_selling", "sort_order", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].user.tenant
        return super().create(validated_data)


class StockReceiptItemWriteSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal("0.001")
    )
    cost_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0")
    )
    sale_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, default=0
    )
    list_prices = serializers.DictField(
        child=serializers.DecimalField(max_digits=14, decimal_places=2),
        required=False,
        default=dict,
    )


class StockReceiptCreateSerializer(serializers.Serializer):
    supplier_id = serializers.UUIDField(required=False, allow_null=True)
    supplier_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    warehouse = serializers.CharField(max_length=120, default="Asosiy")
    currency = serializers.CharField(max_length=10, default="SUM")
    price_list_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    include_selling_price = serializers.BooleanField(default=True)
    items = StockReceiptItemWriteSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Kamida bitta mahsulot kerak.")
        return value

    def create(self, validated_data):
        request = self.context["request"]
        tenant = request.user.tenant
        if not tenant:
            raise serializers.ValidationError({"detail": "Tenant topilmadi."})

        items_data = validated_data.pop("items")
        price_list_ids = [str(x) for x in validated_data.pop("price_list_ids", [])]
        include_selling = validated_data.pop("include_selling_price", True)
        supplier_id = validated_data.pop("supplier_id", None)
        supplier_name = (validated_data.pop("supplier_name", "") or "").strip()

        supplier = None
        if supplier_id:
            from .models import Supplier

            supplier = Supplier.objects.filter(tenant=tenant, id=supplier_id).first()

        with transaction.atomic():
            last = (
                StockReceipt.objects.filter(tenant=tenant)
                .order_by("-receipt_number")
                .values_list("receipt_number", flat=True)
                .first()
            )
            receipt_number = (last or 0) + 1

            receipt = StockReceipt.objects.create(
                tenant=tenant,
                user=request.user,
                supplier=supplier,
                supplier_name=supplier_name or (supplier.name if supplier else ""),
                warehouse=validated_data.get("warehouse") or "Asosiy",
                currency=validated_data.get("currency") or "SUM",
                receipt_number=receipt_number,
                status=StockReceipt.STATUS_COMPLETED,
                price_list_ids=price_list_ids,
                include_selling_price=include_selling,
                completed_at=timezone.now(),
            )

            total = Decimal("0")
            valid_lists = set(
                str(x)
                for x in PriceList.objects.filter(
                    tenant=tenant, id__in=price_list_ids, is_active=True
                ).values_list("id", flat=True)
            )

            for row in items_data:
                product = Product.objects.select_for_update().get(
                    id=row["product_id"], tenant=tenant
                )
                qty = Decimal(str(row["quantity"]))
                cost = Decimal(str(row["cost_price"]))
                sale = Decimal(str(row.get("sale_price") or 0))
                list_prices_raw = row.get("list_prices") or {}
                list_prices = {
                    str(k): str(v) for k, v in list_prices_raw.items() if str(k) in valid_lists
                }

                line_total = cost * qty
                total += line_total

                StockReceiptItem.objects.create(
                    receipt=receipt,
                    product=product,
                    product_name=product.name,
                    quantity=qty,
                    cost_price=cost,
                    sale_price=sale,
                    list_prices=list_prices,
                    line_total=line_total,
                )

                product.quantity = (product.quantity or Decimal("0")) + qty
                product.cost_price = cost
                if include_selling and sale > 0:
                    product.price = sale
                product.save(update_fields=["quantity", "cost_price", "price", "updated_at"])

                for pl_id, price_str in list_prices.items():
                    pl = PriceList.objects.filter(tenant=tenant, id=pl_id).first()
                    if not pl or pl.is_selling:
                        continue
                    ProductPrice.objects.update_or_create(
                        tenant=tenant,
                        product=product,
                        price_list=pl,
                        defaults={"price": Decimal(price_str)},
                    )

            receipt.total = total
            receipt.save(update_fields=["total"])

        return receipt


class StockReceiptItemReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockReceiptItem
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "cost_price",
            "sale_price",
            "list_prices",
            "line_total",
        ]


class StockReceiptReadSerializer(serializers.ModelSerializer):
    items = StockReceiptItemReadSerializer(many=True, read_only=True)

    class Meta:
        model = StockReceipt
        fields = [
            "id",
            "receipt_number",
            "supplier",
            "supplier_name",
            "warehouse",
            "currency",
            "status",
            "price_list_ids",
            "include_selling_price",
            "total",
            "created_at",
            "completed_at",
            "items",
        ]


class StockAuditItemWriteSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity_after = serializers.DecimalField(
        max_digits=14, decimal_places=3, required=False, allow_null=True
    )
    cost_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True
    )
    sale_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True
    )
    list_prices = serializers.DictField(
        child=serializers.DecimalField(max_digits=14, decimal_places=2),
        required=False,
        default=dict,
    )


class StockAuditCreateSerializer(serializers.Serializer):
    warehouse = serializers.CharField(max_length=120, default="Asosiy")
    currency = serializers.CharField(max_length=10, default="SUM")
    price_list_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    include_selling_price = serializers.BooleanField(default=False)
    include_stock = serializers.BooleanField(default=True)
    include_cost_price = serializers.BooleanField(default=False)
    items = StockAuditItemWriteSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Kamida bitta mahsulot kerak.")
        return value

    def create(self, validated_data):
        request = self.context["request"]
        tenant = request.user.tenant
        if not tenant:
            raise serializers.ValidationError({"detail": "Tenant topilmadi."})

        items_data = validated_data.pop("items")
        price_list_ids = [str(x) for x in validated_data.pop("price_list_ids", [])]
        include_selling = validated_data.pop("include_selling_price", False)
        include_stock = validated_data.pop("include_stock", True)
        include_cost = validated_data.pop("include_cost_price", False)

        with transaction.atomic():
            last = (
                StockAudit.objects.filter(tenant=tenant)
                .order_by("-audit_number")
                .values_list("audit_number", flat=True)
                .first()
            )
            audit_number = (last or 0) + 1

            audit = StockAudit.objects.create(
                tenant=tenant,
                user=request.user,
                warehouse=validated_data.get("warehouse") or "Asosiy",
                currency=validated_data.get("currency") or "SUM",
                audit_number=audit_number,
                status=StockAudit.STATUS_COMPLETED,
                price_list_ids=price_list_ids,
                include_selling_price=include_selling,
                include_stock=include_stock,
                include_cost_price=include_cost,
                completed_at=timezone.now(),
            )

            valid_lists = set(
                str(x)
                for x in PriceList.objects.filter(
                    tenant=tenant, id__in=price_list_ids, is_active=True
                ).values_list("id", flat=True)
            )

            for row in items_data:
                product = Product.objects.select_for_update().get(
                    id=row["product_id"], tenant=tenant
                )
                qty_before = product.quantity or Decimal("0")
                qty_after = row.get("quantity_after")
                cost = row.get("cost_price")
                sale = row.get("sale_price")
                list_prices_raw = row.get("list_prices") or {}
                list_prices = {
                    str(k): str(v) for k, v in list_prices_raw.items() if str(k) in valid_lists
                }

                StockAuditItem.objects.create(
                    audit=audit,
                    product=product,
                    product_name=product.name,
                    quantity_before=qty_before,
                    quantity_after=Decimal(str(qty_after)) if qty_after is not None else None,
                    cost_price=Decimal(str(cost)) if cost is not None else None,
                    sale_price=Decimal(str(sale)) if sale is not None else None,
                    list_prices=list_prices,
                )

                update_fields = ["updated_at"]
                if include_stock and qty_after is not None:
                    product.quantity = Decimal(str(qty_after))
                    update_fields.append("quantity")
                if include_cost and cost is not None:
                    product.cost_price = Decimal(str(cost))
                    update_fields.append("cost_price")
                if include_selling and sale is not None:
                    product.price = Decimal(str(sale))
                    update_fields.append("price")
                if len(update_fields) > 1:
                    product.save(update_fields=update_fields)

                for pl_id, price_str in list_prices.items():
                    pl = PriceList.objects.filter(tenant=tenant, id=pl_id).first()
                    if not pl or pl.is_selling:
                        continue
                    ProductPrice.objects.update_or_create(
                        tenant=tenant,
                        product=product,
                        price_list=pl,
                        defaults={"price": Decimal(price_str)},
                    )

        return audit


class StockAuditItemReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockAuditItem
        fields = [
            "id",
            "product",
            "product_name",
            "quantity_before",
            "quantity_after",
            "cost_price",
            "sale_price",
            "list_prices",
        ]


class StockAuditReadSerializer(serializers.ModelSerializer):
    items = StockAuditItemReadSerializer(many=True, read_only=True)

    class Meta:
        model = StockAudit
        fields = [
            "id",
            "audit_number",
            "warehouse",
            "currency",
            "status",
            "price_list_ids",
            "include_selling_price",
            "include_stock",
            "include_cost_price",
            "created_at",
            "completed_at",
            "items",
        ]
