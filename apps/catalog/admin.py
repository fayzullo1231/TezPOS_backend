from decimal import Decimal

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from apps.accounts.models import Tenant

from .barcode_lookup import normalize_barcode, sync_product_barcodes
from .models import (
    Category,
    PriceList,
    Product,
    ProductBarcode,
    ProductImage,
    ProductPrice,
    Supplier,
    UnitOfMeasure,
)


def _tenant_price_lists(tenant) -> list[PriceList]:
    if not tenant:
        return []
    return list(
        PriceList.objects.filter(tenant=tenant, is_active=True).order_by(
            "sort_order", "name"
        )
    )


def _tenant_for_admin(request, obj=None) -> Tenant | None:
    if obj and obj.tenant_id:
        return obj.tenant
    if request.method == "POST":
        tenant_id = request.POST.get("tenant")
        if tenant_id:
            return Tenant.objects.filter(pk=tenant_id).first()
    return None


PRODUCT_MODEL_FIELDS = (
    "tenant",
    "name",
    "barcode",
    "sku",
    "price",
    "cost_price",
    "quantity",
    "unit",
    "unit_ref",
    "category",
    "supplier",
    "image",
    "is_active",
)


class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = PRODUCT_MODEL_FIELDS

    @staticmethod
    def _list_field_name(price_list_id) -> str:
        return f"list_price_{price_list_id}"

    def save(self, commit=True):
        product = super().save(commit=commit)
        if not commit:
            return product

        tenant = product.tenant
        if not tenant:
            return product

        for pl in _tenant_price_lists(tenant):
            if pl.is_selling:
                continue
            field_name = self._list_field_name(pl.id)
            if field_name not in self.fields:
                continue
            raw = self.cleaned_data.get(field_name)
            if raw is None or raw == "":
                ProductPrice.objects.filter(product=product, price_list=pl).delete()
                continue
            ProductPrice.objects.update_or_create(
                tenant=tenant,
                product=product,
                price_list=pl,
                defaults={"price": raw},
            )
        return product


def _build_product_admin_form(tenant, obj=None) -> type[ProductAdminForm]:
    """Dinamik narx maydonlarini form klass atributlari sifatida e'lon qilish."""
    lists = _tenant_price_lists(tenant)
    existing: dict[str, Decimal] = {}
    if obj and obj.pk:
        existing = {
            str(row.price_list_id): row.price
            for row in obj.list_prices.select_related("price_list")
        }

    attrs: dict[str, forms.Field] = {}
    for pl in lists:
        if pl.is_selling:
            continue
        field_name = ProductAdminForm._list_field_name(pl.id)
        attrs[field_name] = forms.DecimalField(
            label=pl.name,
            required=False,
            max_digits=14,
            decimal_places=2,
            initial=existing.get(str(pl.id)),
            help_text=f"Narxlar ro'yxati: {pl.name}",
        )

    DynamicProductForm = type(
        "DynamicProductForm",
        (ProductAdminForm,),
        attrs,
    )

    selling = next((pl for pl in lists if pl.is_selling), None)
    if selling and "price" in DynamicProductForm.base_fields:
        DynamicProductForm.base_fields["price"].label = selling.name
        DynamicProductForm.base_fields["price"].help_text = (
            "Sotuv narxi (kassa chekida sotuv ro'yxati)"
        )
    elif "price" in DynamicProductForm.base_fields:
        DynamicProductForm.base_fields["price"].label = "Sotuv narxi"
        DynamicProductForm.base_fields["price"].help_text = "Asosiy kassa narxi"

    return DynamicProductForm


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "is_active"]


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ["name", "is_weighable", "tenant", "created_at"]
    list_filter = ["is_weighable", "tenant"]


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "phone"]


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "is_selling", "sort_order", "is_active"]
    list_filter = ["is_selling", "is_active", "tenant"]
    search_fields = ["name"]


class ProductBarcodeInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        codes: list[str] = []
        seen: set[str] = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            code = normalize_barcode(form.cleaned_data.get("code", ""))
            if not code:
                continue
            if code in seen:
                raise ValidationError(f"Takroriy shtrix kod: {code}")
            seen.add(code)
            codes.append(code)


class ProductBarcodeInline(admin.TabularInline):
    model = ProductBarcode
    formset = ProductBarcodeInlineFormSet
    extra = 1
    fields = ["code"]
    verbose_name = "Shtrix kod"
    verbose_name_plural = "Shtrix kodlar"


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ["image", "sort_order", "is_primary"]
    verbose_name = "Rasm"
    verbose_name_plural = "Rasmlar"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "barcode", "barcode_count", "price", "quantity", "tenant", "is_active"]
    search_fields = ["name", "barcode", "barcodes__code"]
    inlines = [ProductBarcodeInline, ProductImageInline]

    def get_form(self, request, obj=None, change=False, **kwargs):
        tenant = _tenant_for_admin(request, obj)
        kwargs["form"] = _build_product_admin_form(tenant, obj)
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fieldsets(self, request, obj=None):
        base = [
            "tenant",
            "name",
            "barcode",
            "sku",
            "cost_price",
            "quantity",
            "unit",
            "unit_ref",
            "category",
            "supplier",
            "image",
            "is_active",
        ]
        price_fields: list[str] = ["price"]

        tenant = _tenant_for_admin(request, obj)
        form_class = _build_product_admin_form(tenant, obj)
        for name in form_class.declared_fields:
            if name.startswith("list_price_"):
                price_fields.append(name)

        return (
            (None, {"fields": tuple(base)}),
            (
                "Narxlar ro'yxati",
                {
                    "fields": tuple(price_fields),
                    "description": (
                        "Har bir narx maydoni bazadagi narxlar ro'yxatiga mos keladi. "
                        "Yangi ro'yxat qo'shsangiz, saqlang va qayta oching."
                    ),
                },
            ),
        )

    @admin.display(description="Shtrix kodlar")
    def barcode_count(self, obj):
        return str(obj.barcodes.count())

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        product = form.instance
        for obj in instances:
            if isinstance(obj, ProductBarcode):
                obj.tenant = product.tenant
            obj.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

        codes = list(product.barcodes.values_list("code", flat=True))
        primary = normalize_barcode(product.barcode)
        if primary and primary not in codes:
            codes.insert(0, primary)
        elif primary:
            codes = [primary] + [c for c in codes if c != primary]
        elif codes:
            product.barcode = codes[0]
            product.save(update_fields=["barcode", "updated_at"])
        sync_product_barcodes(product, codes if codes else [])


@admin.register(ProductBarcode)
class ProductBarcodeAdmin(admin.ModelAdmin):
    list_display = ["code", "product", "tenant", "created_at"]
    search_fields = ["code", "product__name"]


@admin.register(ProductPrice)
class ProductPriceAdmin(admin.ModelAdmin):
    list_display = ["product", "price_list", "price", "tenant"]
    list_filter = ["price_list", "tenant"]
    search_fields = ["product__name", "price_list__name"]
