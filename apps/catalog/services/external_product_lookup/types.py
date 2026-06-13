from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ExternalProductResult:
    barcode: str
    name: str
    brand: str
    category: str
    image: str

    def to_dict(self) -> dict:
        return asdict(self)
