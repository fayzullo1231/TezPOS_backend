from __future__ import annotations

from typing import Any

from ..types import ExternalProductResult
from .base import BarcodeLookupProvider
from .http import http_get_json

_NAME_FIELDS = (
    "product_name_uz",
    "product_name_ru",
    "product_name_en",
    "product_name",
    "generic_name_uz",
    "generic_name_ru",
    "generic_name",
    "abbreviated_product_name",
)
_IMAGE_FIELDS = (
    "image_front_url",
    "image_url",
    "image_small_url",
)


class OpenFactsProvider(BarcodeLookupProvider):
    """Open Food / Products / Beauty Facts (open*facts.org)."""

    def __init__(self, *, name: str, api_base: str):
        self.name = name
        self.api_base = api_base.rstrip("/")

    def lookup(self, barcode: str) -> ExternalProductResult | None:
        data = http_get_json(f"{self.api_base}/api/v2/product/{barcode}.json")
        if not data or not isinstance(data, dict):
            return None

        status = data.get("status")
        if status not in (1, "1", "found"):
            return None

        product = data.get("product")
        if not isinstance(product, dict):
            return None

        name = _pick_name(product)
        if not name:
            return None

        brand = _first_text(product.get("brands"), product.get("brand_owner"))
        category = _first_text(product.get("categories"))
        image = _pick_image(product)

        return ExternalProductResult(
            barcode=barcode,
            name=name,
            brand=brand,
            category=category,
            image=image,
        )


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text.split(",")[0].strip()
    return ""


def _pick_name(product: dict) -> str:
    for key in _NAME_FIELDS:
        text = _first_text(product.get(key))
        if text:
            return text
    return ""


def _pick_image(product: dict) -> str:
    for key in _IMAGE_FIELDS:
        text = _first_text(product.get(key))
        if text:
            return text
    return ""
