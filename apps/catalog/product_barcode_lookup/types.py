from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProductLookupResult:
    source: str
    barcode: str
    name: str
    brand: str
    category: str | None = None
    image: str | None = None
    company: str | None = None

    def to_success_dict(self) -> dict:
        payload = {
            "success": True,
            "source": self.source,
            "barcode": self.barcode,
            "name": self.name,
            "brand": self.brand,
            "image": self.image,
            "suggest_create": True,
        }
        if self.category:
            payload["category"] = self.category
        if self.company:
            payload["company"] = self.company
        return payload
