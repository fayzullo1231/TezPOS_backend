"""
Tashqi API (GS1 Registry) orqali shtrix-kod bo'yicha mahsulot qidirish.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .product_barcode_lookup.exceptions import (
    BadResponseError,
    BarcodeLookupError,
    InvalidBarcodeError,
    NetworkError,
    NotFoundError,
    ServerError,
    TimeoutError,
)
from .product_barcode_lookup.services import ProductLookupService


class ExternalBarcodeLookupView(APIView):
    """
    GET /api/catalog/barcode-lookup/?code=5449000000996

    Muvaffaqiyat (200):
    {
      "barcode": "5449000000996",
      "name": "Coca-Cola",
      "brand": "Coca-Cola",
      "category": "Soft Drinks",
      "image": "https://....jpg"
    }

    Topilmasa (404):
    { "success": false, "message": "Mahsulot topilmadi" }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        barcode = (
            request.query_params.get("code")
            or request.query_params.get("barcode")
            or ""
        ).strip()

        if not barcode:
            return Response(
                {
                    "success": False,
                    "error": "invalid_barcode",
                    "message": "Shtrix kod (code) parametri majburiy.",
                },
                status=400,
            )

        try:
            payload = ProductLookupService().lookup(barcode)
            return Response(payload)
        except InvalidBarcodeError as exc:
            return Response(exc.to_dict(), status=400)
        except NotFoundError as exc:
            return Response({"success": False, "message": exc.message}, status=404)
        except TimeoutError as exc:
            return Response(exc.to_dict(), status=504)
        except NetworkError as exc:
            return Response(exc.to_dict(), status=502)
        except (ServerError, BadResponseError) as exc:
            return Response(exc.to_dict(), status=503)
        except BarcodeLookupError as exc:
            return Response(exc.to_dict(), status=500)
