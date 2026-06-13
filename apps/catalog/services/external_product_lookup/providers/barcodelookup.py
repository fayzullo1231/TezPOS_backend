from __future__ import annotations

from django.conf import settings

from ..types import ExternalProductResult
from .base import BarcodeLookupProvider
from .http import http_get_json


class BarcodeLookupComProvider(BarcodeLookupProvider):
    """Barcode Lookup API (BARCODE_LOOKUP_API_KEY kerak)."""

    name = "barcodelookup"

    def lookup(self, barcode: str) -> ExternalProductResult | None:
        api_key = getattr(settings, "BARCODE_LOOKUP_API_KEY", "").strip()
        if not api_key:
            return None

        data = http_get_json(
            "https://api.barcodelookup.com/v3/products"
            f"?barcode={barcode}&formatted=y&key={api_key}"
        )
        if not data or not isinstance(data, dict):
            return None

        products = data.get("products")
        if not isinstance(products, list) or not products:
            return None

        item = products[0]
        if not isinstance(item, dict):
            return None

        name = _first_text(item.get("title"), item.get("product_name"))
        if not name:
            return None

        brand = _first_text(item.get("brand"))
        category = _first_text(item.get("category"))
        images = item.get("images")
        image = ""
        if isinstance(images, list) and images:
            image = _first_text(images[0])

        return ExternalProductResult(
            barcode=barcode,
            name=name,
            brand=brand,
            category=category,
            image=image,
        )


def _first_text(*values) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""
