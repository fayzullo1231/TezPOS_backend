from .providers.barcodelookup import BarcodeLookupComProvider
from .providers.base import BarcodeLookupProvider
from .providers.eansearch import EANSearchProvider
from .providers.openfacts import OpenFactsProvider
from .providers.upcitemdb import UPCItemDBProvider

# Ketma-ket sinab ko'riladi — birinchi topilgan natija qaytariladi.
DEFAULT_PROVIDERS: list[BarcodeLookupProvider] = [
    OpenFactsProvider(name="openfoodfacts", api_base="https://world.openfoodfacts.org"),
    OpenFactsProvider(name="openfoodfacts_ru", api_base="https://ru.openfoodfacts.org"),
    OpenFactsProvider(name="openproductsfacts", api_base="https://world.openproductsfacts.org"),
    OpenFactsProvider(name="openbeautyfacts", api_base="https://world.openbeautyfacts.org"),
    OpenFactsProvider(name="openpetfoodfacts", api_base="https://world.openpetfoodfacts.org"),
    UPCItemDBProvider(),
    BarcodeLookupComProvider(),
    EANSearchProvider(),
]


def get_providers() -> list[BarcodeLookupProvider]:
    return list(DEFAULT_PROVIDERS)
