"""
Tenant-scoped mahsulot API.
URL: /{server_name}/product/
Masalan: https://tezpos.uz/demo/product/
"""

from django.db.models import Q
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import TenantTokenAuthentication
from apps.accounts.models import Tenant, User

from .barcode_lookup import find_product_by_barcode, lookup_external_barcode, normalize_barcode
from .models import Product
from .serializers import ProductListSerializer


class TenantProductListView(APIView):
    """Har bir server (tenant) uchun alohida mahsulotlar ro'yxati."""

    authentication_classes = [TenantTokenAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, server_name: str):
        if not isinstance(request.user, User):
            return Response({"detail": "Autentifikatsiya kerak."}, status=401)

        tenant = request.user.tenant
        if not tenant or tenant.server_name.lower() != server_name.lower():
            return Response({"detail": "Server nomi mos kelmadi."}, status=403)

        products = Product.objects.filter(
            tenant=tenant, is_active=True
        ).select_related("category", "unit_ref").prefetch_related(
            "barcodes", "list_prices__price_list"
        )

        search = (request.query_params.get("search") or "").strip()
        barcode = normalize_barcode(request.query_params.get("barcode") or "")

        if barcode:
            product = find_product_by_barcode(tenant, barcode)
            if product:
                return Response(
                    ProductListSerializer(
                        [product], many=True, context={"request": request}
                    ).data
                )

            external = lookup_external_barcode(barcode)
            if not external:
                return Response([])

            external["found_in_catalog"] = False
            code = external.get("barcode", barcode)
            return Response(
                [
                    {
                        "id": None,
                        "name": external.get("name", ""),
                        "barcode": code,
                        "barcodes": [code],
                        "price": "0.00",
                        "cost_price": "0.00",
                        "quantity": "0.000",
                        "unit": "dona",
                        "unit_ref": None,
                        "unit_is_weighable": False,
                        "category": None,
                        "category_name": external.get("category") or "",
                        "brand": None,
                        "brand_name": external.get("brand") or "",
                        "image_url": external.get("image"),
                        "list_prices": {},
                        "is_active": True,
                        "found_in_catalog": False,
                        "external": True,
                        "source": external.get("source", ""),
                        "suggest_create": True,
                    }
                ]
            )

        if search:
            products = products.filter(
                Q(name__icontains=search)
                | Q(barcode__icontains=search)
                | Q(barcodes__code__icontains=search)
                | Q(sku__icontains=search)
            ).distinct()[:40]
        elif request.query_params.get("all") != "true":
            products = products[:20]

        return Response(
            ProductListSerializer(
                products, many=True, context={"request": request}
            ).data
        )

    def post(self, request, server_name: str):
        if not isinstance(request.user, User):
            return Response({"detail": "Autentifikatsiya kerak."}, status=401)

        tenant = request.user.tenant
        if not tenant or tenant.server_name.lower() != server_name.lower():
            return Response({"detail": "Server nomi mos kelmadi."}, status=403)

        from .serializers import ProductSerializer

        serializer = ProductSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        product = serializer.save(tenant=tenant)
        return Response(
            ProductSerializer(product, context={"request": request}).data,
            status=201,
        )
