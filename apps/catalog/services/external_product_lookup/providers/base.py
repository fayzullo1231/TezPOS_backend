from abc import ABC, abstractmethod

from ..types import ExternalProductResult


class BarcodeLookupProvider(ABC):
    """Kelajakda boshqa API provayderlarini qo'shish uchun asos."""

    name: str = "base"

    @abstractmethod
    def lookup(self, barcode: str) -> ExternalProductResult | None:
        """
        Mahsulot topilsa ExternalProductResult, topilmasa None.
        Tarmoq/server xatolarida exception ko'tariladi.
        """
