from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

from .exceptions import (
    BadResponseError,
    BarcodeLookupError,
    InvalidBarcodeError,
    NetworkError,
    NotFoundError,
    ServerError,
    TimeoutError,
)
from apps.catalog.services.external_product_lookup.exceptions import (
    BadResponseError as ExternalBadResponseError,
)
from apps.catalog.services.external_product_lookup.exceptions import (
    NetworkError as ExternalNetworkError,
)
from apps.catalog.services.external_product_lookup.exceptions import (
    ServerError as ExternalServerError,
)
from apps.catalog.services.external_product_lookup.exceptions import (
    TimeoutError as ExternalTimeoutError,
)
from apps.catalog.services.external_product_lookup.registry import get_providers

from .local_db import lookup_local_barcode
from .types import ProductLookupResult

USER_AGENT = "TezPOS/1.0 (POS; barcode lookup)"
DEFAULT_HTTP_TIMEOUT = 10.0
_GTIN_RE = re.compile(r"^\d{8,14}$")
_LANG_PRIORITY = ("uz", "ru", "en", "tr", "de", "fr", "es")


def normalize_barcode(code: str) -> str:
    return re.sub(r"\D", "", (code or "").strip())


def validate_barcode(code: str) -> str:
    normalized = normalize_barcode(code)
    if not _GTIN_RE.fullmatch(normalized):
        raise InvalidBarcodeError()
    return normalized


def to_gtin14(code: str) -> str:
    digits = normalize_barcode(code)
    if len(digits) <= 14:
        return digits.zfill(14)
    return digits[-14:]


def _first_non_empty(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _localized_field(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        for lang in _LANG_PRIORITY:
            for item in value:
                if not isinstance(item, dict):
                    continue
                if item.get("language") == lang and item.get("value"):
                    return str(item["value"]).strip()
        for item in value:
            if isinstance(item, dict) and item.get("value"):
                return str(item["value"]).strip()
        return ""
    return str(value).strip()


def _http_get_json(url: str, timeout: float = DEFAULT_HTTP_TIMEOUT) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    return _read_json_response(request, timeout)


def _http_post_json(
    url: str,
    payload: dict,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> Any:
    merged = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if headers:
        merged.update(headers)
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=merged, method="POST")
    return _read_json_response(request, timeout)


def _read_json_response(request: urllib.request.Request, timeout: float) -> Any:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code >= 500:
            raise ServerError() from exc
        raise BadResponseError() from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise TimeoutError() from exc
        raise NetworkError() from exc
    except TimeoutError as exc:
        raise TimeoutError() from exc
    except OSError as exc:
        if "timed out" in str(exc).lower():
            raise TimeoutError() from exc
        raise NetworkError() from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BadResponseError() from exc


class LocalBarcodeService:
    """Ichki (lokal) shtrix-kod bazasi."""

    def lookup(self, barcode: str) -> ProductLookupResult | None:
        code = validate_barcode(barcode)
        row = lookup_local_barcode(code)
        if not row or not row.get("name"):
            return None

        image = row.get("image") or None
        return ProductLookupResult(
            source="local",
            barcode=code,
            name=row["name"],
            brand=row.get("brand", ""),
            category=row.get("category") or None,
            image=image or None,
        )


class GS1Service:
    """
    GS1 Global Registry (GRP API) orqali shtrix-kod qidiruv.

    GS1 Uzbekistan yoki boshqa MO dan API kalit olinadi:
    GS1_REGISTRY_API_URL, GS1_REGISTRY_API_KEY
    """

    def __init__(self, timeout: float = DEFAULT_HTTP_TIMEOUT):
        self.timeout = timeout
        self.api_url = getattr(settings, "GS1_REGISTRY_API_URL", "").strip().rstrip("/")
        self.api_key = getattr(settings, "GS1_REGISTRY_API_KEY", "").strip()
        self.api_key_header = getattr(
            settings, "GS1_REGISTRY_API_KEY_HEADER", "Ocp-Apim-Subscription-Key"
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_url and self.api_key)

    def lookup(self, barcode: str) -> ProductLookupResult | None:
        if not self.is_configured:
            return None

        code = validate_barcode(barcode)
        gtin14 = to_gtin14(code)
        headers = {self.api_key_header: self.api_key}
        data = self._query_gtin(gtin14, headers)
        if data is None:
            return None

        record = self._extract_gtin_record(data, gtin14, code)
        if not record:
            return None

        name = _localized_field(record.get("productDescription"))
        brand = _localized_field(record.get("brandName"))
        company = ""
        licence = record.get("gs1Licence")
        if isinstance(licence, dict):
            company = _first_non_empty(licence.get("licenseeName"))

        if not name and not brand:
            return None

        image = None
        images = record.get("productImageUrl")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                image = _first_non_empty(first.get("value"), first.get("url"))
            else:
                image = _first_non_empty(first)

        return ProductLookupResult(
            source="gs1",
            barcode=code,
            name=name or brand,
            brand=brand,
            company=company or None,
            image=image or None,
        )

    def _query_gtin(self, gtin14: str, headers: dict[str, str]) -> Any:
        endpoints = (
            f"{self.api_url}/gtins/verified",
            f"{self.api_url}/gtin/verified",
            self.api_url,
        )
        bodies: list[Any] = [{"gtins": [gtin14]}, [gtin14], {"gtin": gtin14}]

        last_error: BarcodeLookupError | None = None
        for endpoint in endpoints:
            for body in bodies:
                try:
                    data = _http_post_json(
                        endpoint, body, headers=headers, timeout=self.timeout
                    )
                    if data is not None:
                        return data
                except (NetworkError, TimeoutError, ServerError, BadResponseError) as exc:
                    last_error = exc
                    continue
        if last_error:
            raise last_error
        return None

    @staticmethod
    def _extract_gtin_record(data: Any, gtin14: str, raw_code: str) -> dict | None:
        rows: list[dict] = []
        if isinstance(data, list):
            rows = [row for row in data if isinstance(row, dict)]
        elif isinstance(data, dict):
            for key in ("gtins", "items", "results", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    rows = [row for row in value if isinstance(row, dict)]
                    break
            if not rows and data.get("gtin"):
                rows = [data]

        if not rows:
            return None

        normalized_targets = {
            gtin14,
            gtin14.lstrip("0"),
            raw_code,
            raw_code.lstrip("0"),
        }
        for row in rows:
            gtin = _first_non_empty(row.get("gtin"), row.get("GTIN"))
            if gtin in normalized_targets or gtin.lstrip("0") in normalized_targets:
                status = str(row.get("gtinRecordStatus", "OK")).upper()
                if status and status not in {"OK", "ACTIVE"}:
                    continue
                return row

        first = rows[0]
        status = str(first.get("gtinRecordStatus", "OK")).upper()
        if status and status not in {"OK", "ACTIVE"}:
            return None
        return first


class ExternalProvidersService:
    """Open Food Facts, UPC Item DB va boshqa ochiq API lar."""

    def lookup(self, barcode: str) -> ProductLookupResult | None:
        code = validate_barcode(barcode)
        for provider in get_providers():
            try:
                result = provider.lookup(code)
            except (
                ExternalNetworkError,
                ExternalTimeoutError,
                ExternalServerError,
                ExternalBadResponseError,
            ):
                continue
            if result is not None and result.name:
                return ProductLookupResult(
                    source=provider.name,
                    barcode=code,
                    name=result.name,
                    brand=result.brand,
                    category=result.category or None,
                    image=result.image or None,
                )
        return None


class ProductLookupService:
    """Lokal baza → GS1 Registry → ochiq API lar → topilmadi."""

    def __init__(
        self,
        local: LocalBarcodeService | None = None,
        gs1: GS1Service | None = None,
        external: ExternalProvidersService | None = None,
    ):
        self.local = local or LocalBarcodeService()
        self.gs1 = gs1 or GS1Service()
        self.external = external or ExternalProvidersService()

    def lookup(self, barcode: str) -> dict:
        code = validate_barcode(barcode)
        infra_error: BarcodeLookupError | None = None

        for service in (self.local, self.gs1, self.external):
            try:
                result = service.lookup(code)
            except (NetworkError, TimeoutError, ServerError, BadResponseError) as exc:
                infra_error = exc
                continue
            except InvalidBarcodeError:
                raise

            if result is not None:
                return result.to_success_dict()

        if infra_error is not None:
            raise infra_error

        raise NotFoundError()
