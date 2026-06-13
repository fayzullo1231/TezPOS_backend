from __future__ import annotations

from django.conf import settings

from ..types import ExternalProductResult
from .base import BarcodeLookupProvider
from .http import http_get_json


class EANSearchProvider(BarcodeLookupProvider):
    """EAN-Search.org (EAN_SEARCH_API_TOKEN ixtiyoriy — tokensiz sinab ko'riladi)."""

    name = "eansearch"

    def lookup(self, barcode: str) -> ExternalProductResult | None:
        token = getattr(settings, "EAN_SEARCH_API_TOKEN", "").strip()
        if not token:
            return None

        data = http_get_json(
            "https://api.ean-search.org/api"
            f"?token={token}&op=barcode-lookup&format=json&ean={barcode}"
        )
        if not data or not isinstance(data, dict):
            return None

        name = _first_text(data.get("name"))
        if not name:
            return None

        return ExternalProductResult(
            barcode=barcode,
            name=name,
            brand=_first_text(data.get("vendor"), data.get("brand")),
            category=_first_text(data.get("categoryName")),
            image="",
        )


def _first_text(*values) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""
