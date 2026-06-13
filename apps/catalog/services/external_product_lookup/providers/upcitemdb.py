from __future__ import annotations

from ..types import ExternalProductResult
from .base import BarcodeLookupProvider
from .http import http_get_json


class UPCItemDBProvider(BarcodeLookupProvider):
    """UPC Item DB (trial endpoint — kalitsiz, cheklangan)."""

    name = "upcitemdb"
    api_url = "https://api.upcitemdb.com/prod/trial/lookup"

    def lookup(self, barcode: str) -> ExternalProductResult | None:
        data = http_get_json(f"{self.api_url}?upc={barcode}")
        if not data or not isinstance(data, dict):
            return None

        items = data.get("items")
        if not isinstance(items, list) or not items:
            return None

        item = items[0]
        if not isinstance(item, dict):
            return None

        name = _first_text(item.get("title"), item.get("description"))
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
