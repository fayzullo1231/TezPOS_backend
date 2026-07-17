"""Shtrix kod bo'yicha mahsulot qidirish."""

from __future__ import annotations

from .models import Product, ProductBarcode


def normalize_barcode(code: str) -> str:
    return (code or "").strip().replace(" ", "")


def find_product_by_barcode(tenant, code: str) -> Product | None:
    code = normalize_barcode(code)
    if not code:
        return None

    base_qs = Product.objects.filter(tenant=tenant, is_active=True).select_related(
        "category", "unit_ref", "supplier"
    ).prefetch_related("barcodes")

    product = base_qs.filter(barcode=code).first()
    if product:
        return product

    pb = (
        ProductBarcode.objects.filter(tenant=tenant, code=code)
        .select_related("product")
        .first()
    )
    if pb and pb.product.is_active:
        return pb.product

    return None


def sync_product_barcodes(product: Product, codes: list[str]) -> None:
    """Mahsulot shtrix kodlarini yangilash (cheksiz)."""
    tenant = product.tenant
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        code = normalize_barcode(raw)
        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append(code)

    if not normalized:
        ProductBarcode.objects.filter(product=product).delete()
        product.barcode = ""
        product.save(update_fields=["barcode", "updated_at"])
        return

    for code in normalized:
        existing = ProductBarcode.objects.filter(tenant=tenant, code=code).select_related(
            "product"
        ).first()
        if existing and existing.product_id != product.id:
            other = existing.product
            other_name = (other.name or "").strip() or f"#{other.id}"
            raise ValueError(
                f"Shtrix kod {code} — «{other_name}» mahsulotida bor"
            )

        # Asosiy barcode maydonida ham bo'lishi mumkin
        other_primary = (
            Product.objects.filter(tenant=tenant, barcode=code)
            .exclude(id=product.id)
            .first()
        )
        if other_primary:
            other_name = (other_primary.name or "").strip() or f"#{other_primary.id}"
            raise ValueError(
                f"Shtrix kod {code} — «{other_name}» mahsulotida bor"
            )

    ProductBarcode.objects.filter(product=product).exclude(code__in=normalized).delete()

    for code in normalized:
        ProductBarcode.objects.update_or_create(
            tenant=tenant,
            code=code,
            defaults={"product": product},
        )

    product.barcode = normalized[0]
    product.save(update_fields=["barcode", "updated_at"])


def lookup_external_barcode(code: str) -> dict | None:
    """Tashqi API lar orqali shtrix-kod bo'yicha mahsulot qidirish."""
    from .product_barcode_lookup.exceptions import InvalidBarcodeError, NotFoundError
    from .product_barcode_lookup.services import ProductLookupService

    normalized = normalize_barcode(code)
    if not normalized:
        return None
    try:
        return ProductLookupService().lookup(normalized)
    except (InvalidBarcodeError, NotFoundError):
        return None
