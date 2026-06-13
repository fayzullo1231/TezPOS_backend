from __future__ import annotations

import re

from .exceptions import (
    ExternalLookupError,
    InvalidBarcodeError,
    NetworkError,
    ProductNotFoundError,
    ServerError,
    TimeoutError,
)
from .providers.base import BarcodeLookupProvider
from .registry import get_providers
from .types import ExternalProductResult

_BARCODE_RE = re.compile(r"^\d{8,14}$")


def normalize_gtin_barcode(code: str) -> str:
    """EAN / UPC / GTIN: faqat raqamlar, 8–14 belgi."""
    digits = re.sub(r"\D", "", (code or "").strip())
    return digits


def validate_barcode(code: str) -> str:
    normalized = normalize_gtin_barcode(code)
    if not _BARCODE_RE.fullmatch(normalized):
        raise InvalidBarcodeError()
    return normalized


class ExternalProductLookupService:
    """Tashqi API orqali shtrix-kod bo'yicha mahsulot qidirish."""

    def __init__(self, providers: list[BarcodeLookupProvider] | None = None):
        self.providers = providers if providers is not None else get_providers()

    def lookup(self, barcode: str) -> ExternalProductResult:
        code = validate_barcode(barcode)

        last_error: ExternalLookupError | None = None
        for provider in self.providers:
            try:
                result = provider.lookup(code)
            except (NetworkError, TimeoutError, ServerError) as exc:
                last_error = exc
                continue

            if result is not None:
                return result

        if last_error is not None:
            raise last_error

        raise ProductNotFoundError()


def lookup_external_product(barcode: str) -> dict:
    """
    API view uchun yagona kirish nuqtasi.
    Muvaffaqiyat: mahsulot maydonlari.
    Topilmasa/xato: success=false bilan JSON.
    """
    try:
        result = ExternalProductLookupService().lookup(barcode)
        return result.to_dict()
    except ProductNotFoundError as exc:
        return {"success": False, "message": exc.message}
    except ExternalLookupError as exc:
        return exc.to_dict()
