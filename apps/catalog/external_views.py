"""
Tashqi sayt/programmalar uchun API.
Har bir so'rov: X-Server-Name + Authorization: Token <api_token>
"""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import TenantTokenAuthentication
from apps.accounts.models import User

from .models import Product
from .serializers import ProductListSerializer


class ExternalProductListView(APIView):
    authentication_classes = [TenantTokenAuthentication]
    permission_classes = [AllowAny]

    def get(self, request):
        if not isinstance(request.user, User):
            return Response({"detail": "Autentifikatsiya kerak."}, status=401)

        products = Product.objects.filter(
            tenant=request.user.tenant, is_active=True
        ).select_related("category")
        return Response(
            ProductListSerializer(
                products, many=True, context={"request": request}
            ).data
        )


class ExternalProductCreateView(APIView):
    authentication_classes = [TenantTokenAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        if not isinstance(request.user, User):
            return Response({"detail": "Autentifikatsiya kerak."}, status=401)

        from .serializers import ProductSerializer

        serializer = ProductSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        product = serializer.save(tenant=request.user.tenant)
        return Response(
            ProductSerializer(product, context={"request": request}).data,
            status=201,
        )
