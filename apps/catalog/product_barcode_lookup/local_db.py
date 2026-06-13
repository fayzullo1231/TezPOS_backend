"""TezPOS ichki shtrix-kod bazasi (GS1 dan oldin tekshiriladi)."""

from __future__ import annotations

LOCAL_PRODUCTS: dict[str, dict[str, str]] = {
    "4780033020027": {
        "name": "Sut 3.2% 1L",
        "brand": "O'zbekiston sut",
        "category": "Sut mahsulotlari",
    },
    "4870206411582": {
        "name": "Non 500g",
        "brand": "Milliy non",
        "category": "Non mahsulotlari",
    },
    "5449000131836": {
        "name": "Coca-Cola 0.5L",
        "brand": "Coca-Cola",
        "category": "Ichimliklar",
    },
    "5449000017673": {
        "name": "Fanta 0.5L",
        "brand": "Fanta",
        "category": "Ichimliklar",
    },
    "5449000000996": {
        "name": "Coca-Cola 0.33L",
        "brand": "Coca-Cola",
        "category": "Ichimliklar",
    },
    "7622300293130": {
        "name": "Milka shokolad 90g",
        "brand": "Milka",
        "category": "Shirinliklar",
    },
    "8715700033235": {
        "name": "Ketchup P'tits Heinz",
        "brand": "Heinz",
        "category": "Ketchup",
    },
}


def lookup_local_barcode(code: str) -> dict[str, str] | None:
    row = LOCAL_PRODUCTS.get(code)
    if not row:
        return None
    return {
        "name": row.get("name", ""),
        "brand": row.get("brand", ""),
        "category": row.get("category", ""),
        "image": row.get("image", ""),
    }
