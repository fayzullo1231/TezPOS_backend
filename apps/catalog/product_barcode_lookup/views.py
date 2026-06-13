from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import (
    BadResponseError,
    BarcodeLookupError,
    InvalidBarcodeError,
    NetworkError,
    NotFoundError,
    ServerError,
    TimeoutError,
)
from .services import ProductLookupService


class ProductBarcodeLookupView(APIView):
    """
    GET /api/products/barcode/{barcode}/

    Ketma-ketlik: Lokal baza → GS1 Registry → Open Food Facts →
    Open Products Facts → Open Beauty Facts → UPC Item DB → ...
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, barcode: str):
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
