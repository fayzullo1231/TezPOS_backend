from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from .barcode_lookup import normalize_barcode, sync_product_barcodes
from .models import Brand, Category, PriceList, Product, ProductImage, ProductPrice, Supplier, UnitOfMeasure


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "parent", "sort_order", "is_active"]
        read_only_fields = ["id"]


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "phone", "address"]
        read_only_fields = ["id"]


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ["id", "name", "is_weighable", "created_at"]
        read_only_fields = ["id", "created_at"]


def _selling_price_list_for_tenant(tenant_id):
    selling_list = PriceList.objects.filter(
        tenant=tenant_id, is_active=True, is_selling=True
    ).first()
    if selling_list:
        return selling_list
    for pl in PriceList.objects.filter(
        tenant=tenant_id, is_active=True
    ).order_by("sort_order", "name"):
        lower = pl.name.lower()
        if (
            "продаж" in lower
            or "sotuv" in lower
            or "sotish" in lower
            or "розниц" in lower
        ):
            return pl
    return None


def product_list_prices_dict(instance) -> dict[str, str]:
    """Faqat sotuv bo'lmagan narxlar ro'yxatlari (optom va h.k.). Sotuv narxi — `product.price`."""
    return {
        str(row.price_list_id): str(row.price)
        for row in instance.list_prices.select_related("price_list").filter(
            price_list__is_active=True,
            price_list__is_selling=False,
        )
    }


def product_image_url(image_field, request) -> str | None:
    if not image_field:
        return None
    if request:
        return request.build_absolute_uri(image_field.url)
    return image_field.url


def product_images_payload(product, request) -> list[dict]:
    rows = []
    for row in product.images.all():
        rows.append(
            {
                "id": str(row.id),
                "url": product_image_url(row.image, request),
                "sort_order": row.sort_order,
                "is_primary": row.is_primary,
            }
        )
    return rows


def product_primary_image_url(product, request) -> str | None:
    primary = product.images.filter(is_primary=True).order_by("sort_order").first()
    if not primary:
        primary = product.images.order_by("sort_order", "created_at").first()
    if primary and primary.image:
        return product_image_url(primary.image, request)
    return product_image_url(product.image, request)


def attach_product_image(product: Product, image_file, *, is_primary: bool | None = None) -> ProductImage:
    count = product.images.count()
    primary = is_primary if is_primary is not None else count == 0
    if primary:
        product.images.update(is_primary=False)
    row = ProductImage.objects.create(
        tenant=product.tenant,
        product=product,
        image=image_file,
        sort_order=count,
        is_primary=primary,
    )
    if primary and product.image != row.image:
        product.image = row.image
        product.save(update_fields=["image", "updated_at"])
    return row


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    brand_name = serializers.CharField(source="brand.name", read_only=True, default="")
    image_url = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    # write_only: modelda ham `barcodes` related_name bor — read uchun to_representation
    barcodes = serializers.ListField(
        child=serializers.CharField(max_length=64, allow_blank=True),
        required=False,
        allow_empty=True,
        write_only=True,
    )
    unit_is_weighable = serializers.SerializerMethodField()
    list_prices = serializers.JSONField(required=False)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "barcode",
            "barcodes",
            "sku",
            "price",
            "cost_price",
            "quantity",
            "unit",
            "unit_ref",
            "unit_is_weighable",
            "category",
            "category_name",
            "brand",
            "brand_name",
            "supplier",
            "image",
            "image_url",
            "images",
            "list_prices",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "image_url", "images", "unit_is_weighable"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        return product_primary_image_url(obj, request)

    def get_images(self, obj):
        request = self.context.get("request")
        return product_images_payload(obj, request)

    def get_unit_is_weighable(self, obj):
        if obj.unit_ref_id:
            return obj.unit_ref.is_weighable
        return obj.unit.lower() in {"kg", "кг", "kilogramm", "kilogram", "g", "gr", "gramm", "грамм"}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["barcodes"] = list(instance.barcodes.values_list("code", flat=True))
        data["list_prices"] = product_list_prices_dict(instance)
        return data

    def _active_price_lists(self, tenant):
        return PriceList.objects.filter(
            tenant=tenant, is_active=True, is_selling=False
        ).order_by("sort_order", "name")

    def _parse_list_prices(self, raw) -> dict[str, Decimal]:
        if raw is None:
            return {}
        if isinstance(raw, str):
            import json

            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raise serializers.ValidationError(
                    {"list_prices": "Noto'g'ri JSON format."}
                ) from None
        if not isinstance(raw, dict):
            raise serializers.ValidationError(
                {"list_prices": "Narxlar ro'yxati obyekt ko'rinishida bo'lishi kerak."}
            )
        parsed: dict[str, Decimal] = {}
        for key, val in raw.items():
            if val is None or str(val).strip() == "":
                continue
            try:
                parsed[str(key)] = Decimal(
                    str(val).replace(",", ".").replace(" ", "").replace("\u00a0", "")
                ).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError) as exc:
                raise serializers.ValidationError(
                    {"list_prices": f"Noto'g'ri narx: {val}"}
                ) from exc
        return parsed

    def validate_list_prices(self, value):
        request = self.context.get("request")
        tenant = getattr(request.user, "tenant", None) if request else None
        if not tenant:
            return value
        parsed = self._parse_list_prices(value)
        required = list(self._active_price_lists(tenant))
        missing = [pl.name for pl in required if str(pl.id) not in parsed]
        if missing:
            raise serializers.ValidationError(
                f"Quyidagi narxlar majburiy: {', '.join(missing)}"
            )
        for pl_id, amount in parsed.items():
            if amount < 0:
                raise serializers.ValidationError("Narx manfiy bo'lmasligi kerak.")
        return parsed

    def _sync_list_prices(self, product, list_prices: dict[str, Decimal] | None):
        if list_prices is None:
            return
        tenant = product.tenant
        active_ids = {
            str(x)
            for x in self._active_price_lists(tenant).values_list("id", flat=True)
        }
        for pl_id, price in list_prices.items():
            if pl_id not in active_ids:
                continue
            ProductPrice.objects.update_or_create(
                tenant=tenant,
                product=product,
                price_list_id=pl_id,
                defaults={"price": price},
            )

    def _parse_barcodes_raw(self, raw):
        """Multipart/JSON dan kelgan barcodes ni ro'yxatga aylantiradi."""
        import json

        if raw is None:
            return None
        if isinstance(raw, list):
            return raw
        if isinstance(raw, (int, float)):
            return [str(raw)]
        if isinstance(raw, str):
            stripped = raw.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    return [raw]
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, (int, float)):
                    return [str(parsed)]
                return [raw]
            return [raw]
        if hasattr(raw, "__iter__") and not isinstance(raw, (str, bytes)):
            return list(raw)
        return [str(raw)]

    def _coerce_request_data(self, data):
        """QueryDict ni oddiy dict ga; barcodes uchun getlist."""
        if not hasattr(data, "get"):
            return data
        if not hasattr(data, "keys"):
            return dict(data)
        result = {}
        for key in data.keys():
            if key == "barcodes" and hasattr(data, "getlist"):
                result[key] = data.getlist("barcodes")
            elif hasattr(data, "getlist"):
                values = data.getlist(key)
                result[key] = values[0] if len(values) == 1 else values
            else:
                result[key] = data.get(key)
        return result

    def run_validation(self, data=serializers.empty):
        if data is not serializers.empty and hasattr(data, "get"):
            import json

            data = self._coerce_request_data(data)
            if "barcodes" in data:
                data["barcodes"] = self._parse_barcodes_raw(data.get("barcodes"))
            raw_lp = data.get("list_prices")
            if isinstance(raw_lp, str) and str(raw_lp).strip():
                try:
                    data["list_prices"] = json.loads(raw_lp)
                except json.JSONDecodeError as exc:
                    raise serializers.ValidationError(
                        {"list_prices": "Noto'g'ri JSON format."}
                    ) from exc
        return super().run_validation(data)

    def _parse_barcodes(self, raw_codes, primary: str = "") -> list[str]:
        codes: list[str] = []
        if raw_codes is not None:
            parsed = self._parse_barcodes_raw(raw_codes)
            if parsed:
                codes = [normalize_barcode(c) for c in parsed if normalize_barcode(c)]
        primary = normalize_barcode(primary)
        if primary and primary not in codes:
            codes.insert(0, primary)
        elif primary and not codes:
            codes = [primary]
        deduped: list[str] = []
        seen: set[str] = set()
        for code in codes:
            if code not in seen:
                seen.add(code)
                deduped.append(code)
        return deduped

    def validate(self, attrs):
        has_barcodes = "barcodes" in attrs
        if has_barcodes:
            raw = attrs.pop("barcodes")
            primary = attrs.get(
                "barcode",
                getattr(self.instance, "barcode", "") if self.instance else "",
            )
            barcodes = self._parse_barcodes(raw, str(primary or ""))
            attrs["_barcodes"] = barcodes
            if barcodes:
                attrs["barcode"] = barcodes[0]
            elif "barcode" in attrs:
                attrs["barcode"] = ""
        elif attrs.get("barcode"):
            primary = normalize_barcode(str(attrs["barcode"]))
            if self.instance:
                existing = list(self.instance.barcodes.values_list("code", flat=True))
                if primary in existing:
                    merged = [primary] + [c for c in existing if c != primary]
                else:
                    merged = [primary] + existing
                attrs["_barcodes"] = merged
            else:
                attrs["_barcodes"] = [primary]
            attrs["barcode"] = primary
        request = self.context.get("request")
        tenant = getattr(getattr(request, "user", None), "tenant", None) if request else None
        if tenant and not getattr(self, "partial", False):
            if self._active_price_lists(tenant).exists() and "list_prices" not in attrs:
                raise serializers.ValidationError(
                    {"list_prices": "Barcha narxlar ro'yxati narxlari majburiy."}
                )
        return attrs

    def _sync_unit(self, validated_data, instance=None):
        unit_ref = validated_data.get("unit_ref")
        if unit_ref is not None:
            validated_data["unit"] = unit_ref.name
        elif instance and "unit" in validated_data and not validated_data.get("unit_ref"):
            name = validated_data["unit"].strip()
            tenant = instance.tenant if instance else self.context["request"].user.tenant
            ref = UnitOfMeasure.objects.filter(tenant=tenant, name__iexact=name).first()
            if ref:
                validated_data["unit_ref"] = ref
        return validated_data

    def create(self, validated_data):
        barcodes = validated_data.pop("_barcodes", [])
        list_prices = validated_data.pop("list_prices", None)
        image = validated_data.pop("image", None)
        validated_data["tenant"] = self.context["request"].user.tenant
        validated_data = self._sync_unit(validated_data)
        product = super().create(validated_data)
        try:
            sync_product_barcodes(product, barcodes)
            self._sync_list_prices(product, list_prices)
            if image:
                attach_product_image(product, image, is_primary=True)
        except ValueError as exc:
            product.delete()
            raise serializers.ValidationError({"barcodes": str(exc)}) from exc
        return product

    def update(self, instance, validated_data):
        barcodes = validated_data.pop("_barcodes", None)
        list_prices = validated_data.pop("list_prices", None)
        image = validated_data.pop("image", None)
        validated_data = self._sync_unit(validated_data, instance)
        product = super().update(instance, validated_data)
        if barcodes is not None:
            try:
                sync_product_barcodes(product, barcodes)
            except ValueError as exc:
                raise serializers.ValidationError({"barcodes": str(exc)}) from exc
        if list_prices is not None:
            self._sync_list_prices(product, list_prices)
        if image:
            attach_product_image(product, image, is_primary=product.images.count() == 0)
        return product


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    brand_name = serializers.CharField(source="brand.name", read_only=True, default="")
    image_url = serializers.SerializerMethodField()
    barcodes = serializers.SerializerMethodField()
    unit_is_weighable = serializers.SerializerMethodField()
    list_prices = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "barcode",
            "barcodes",
            "price",
            "cost_price",
            "quantity",
            "unit",
            "unit_ref",
            "unit_is_weighable",
            "category",
            "category_name",
            "brand",
            "brand_name",
            "image_url",
            "list_prices",
            "is_active",
        ]

    def get_unit_is_weighable(self, obj):
        if obj.unit_ref_id:
            return obj.unit_ref.is_weighable
        return obj.unit.lower() in {"kg", "кг", "kilogramm", "kilogram", "g", "gr", "gramm", "грамм"}

    def get_image_url(self, obj):
        request = self.context.get("request")
        return product_primary_image_url(obj, request)

    def get_barcodes(self, obj):
        return list(obj.barcodes.values_list("code", flat=True))

    def get_list_prices(self, obj):
        return product_list_prices_dict(obj)
