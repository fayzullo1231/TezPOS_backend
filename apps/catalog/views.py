from django.db.models import Q
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .barcode_lookup import (
    find_product_by_barcode,
    lookup_external_barcode,
    normalize_barcode,
)
from .import_excel import import_products_from_excel, preview_excel_columns
from .template_excel import build_import_template
from .models import Brand, Category, Product, ProductImage, Supplier, UnitOfMeasure
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    ProductListSerializer,
    ProductSerializer,
    SupplierSerializer,
    UnitOfMeasureSerializer,
    attach_product_image,
    product_images_payload,
)


class TenantMixin:
    def get_queryset(self):
        return self.queryset.filter(tenant=self.request.user.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


class CategoryViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def paginate_queryset(self, queryset):
        if self.action == "list" and self.request.query_params.get("all") == "true":
            return None
        return super().paginate_queryset(queryset)


class BrandViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer

    def paginate_queryset(self, queryset):
        if self.action == "list" and self.request.query_params.get("all") == "true":
            return None
        return super().paginate_queryset(queryset)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SupplierViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer

    def paginate_queryset(self, queryset):
        if self.action == "list" and self.request.query_params.get("all") == "true":
            return None
        return super().paginate_queryset(queryset)


class UnitOfMeasureViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer

    def paginate_queryset(self, queryset):
        if self.action == "list" and self.request.query_params.get("all") == "true":
            return None
        return super().paginate_queryset(queryset)


class ProductViewSet(TenantMixin, viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category", "supplier", "unit_ref").prefetch_related(
        "barcodes", "list_prices__price_list", "images"
    )
    serializer_class = ProductSerializer

    @staticmethod
    def _external_product_payload(external: dict) -> dict:
        code = external.get("barcode", "")
        return {
            "id": None,
            "name": external.get("name", ""),
            "barcode": code,
            "barcodes": [code] if code else [],
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
            "success": external.get("success", True),
            "suggest_create": True,
        }

    def list(self, request, *args, **kwargs):
        code = normalize_barcode(request.query_params.get("barcode", ""))
        if code:
            product = find_product_by_barcode(request.user.tenant, code)
            if product:
                data = ProductListSerializer(
                    [product], many=True, context={"request": request}
                ).data
                for item in data:
                    item["found_in_catalog"] = True
                return Response(data)

            external = lookup_external_barcode(code)
            if external:
                external["found_in_catalog"] = False
                return Response([self._external_product_payload(external)])

            return Response([])

        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        return ProductSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def paginate_queryset(self, queryset):
        if self.action == "list" and self.request.query_params.get("all") == "true":
            return None
        return super().paginate_queryset(queryset)

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        barcode = self.request.query_params.get("barcode", "").strip()
        category = self.request.query_params.get("category")

        if barcode:
            code = normalize_barcode(barcode)
            product = find_product_by_barcode(self.request.user.tenant, code)
            if product:
                return Product.objects.filter(pk=product.pk)
            return qs.none()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(barcode__icontains=search)
                | Q(barcodes__code__icontains=search)
                | Q(sku__icontains=search)
            ).distinct()
        if category:
            qs = qs.filter(category_id=category)

        if self.action in ("retrieve", "update", "partial_update", "destroy"):
            return qs

        if self.action == "list":
            if self.request.query_params.get("all") == "true":
                return qs
            if not search and not barcode and not category:
                return qs.filter(is_active=True)[:200]
        return qs.filter(is_active=True)

    def perform_destroy(self, instance):
        """Sotuvda ishlatilgan mahsulot — yumshoq o'chirish; aks holda bazadan o'chirish."""
        from apps.sales.models import SaleItem

        if SaleItem.objects.filter(product=instance).exists():
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
            return
        instance.delete()

    @action(detail=False, methods=["get"])
    def count(self, request):
        qs = Product.objects.filter(tenant=request.user.tenant)
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(barcode__icontains=search)
                | Q(barcodes__code__icontains=search)
                | Q(sku__icontains=search)
            ).distinct()
        return Response({"count": qs.count()})

    @action(detail=False, methods=["get"], url_path="by_barcode")
    def by_barcode(self, request):
        code = normalize_barcode(request.query_params.get("code", ""))
        if not code:
            return Response({"detail": "Barcode kerak."}, status=400)
        product = find_product_by_barcode(request.user.tenant, code)
        if product:
            data = ProductSerializer(product, context={"request": request}).data
            data["found_in_catalog"] = True
            return Response(data)

        external = lookup_external_barcode(code)
        if external:
            payload = self._external_product_payload(external)
            payload["suggest_create"] = True
            return Response(payload)

        return Response(
            {
                "detail": "Mahsulot topilmadi.",
                "barcode": code,
                "found_in_catalog": False,
                "suggest_create": True,
            },
            status=404,
        )

    @action(detail=False, methods=["get"], url_path="import-template")
    def import_template(self, request):
        content = build_import_template(tenant=request.user.tenant)
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="tezpos_mahsulot_shablon.xlsx"'
        return response

    @action(
        detail=False,
        methods=["post"],
        url_path="import-preview",
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_preview(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "Excel fayl yuklang."}, status=status.HTTP_400_BAD_REQUEST)

        name_lower = (uploaded.name or "").lower()
        if not name_lower.endswith((".xlsx", ".xlsm")):
            return Response(
                {"detail": "Faqat .xlsx yoki .xlsm fayllar qabul qilinadi."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = preview_excel_columns(uploaded, tenant=request.user.tenant)
        except Exception as exc:
            return Response(
                {"detail": f"Faylni o'qib bo'lmadi: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(data)

    @action(
        detail=False,
        methods=["post"],
        url_path="import",
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_excel(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "Excel fayl yuklang."}, status=status.HTTP_400_BAD_REQUEST)

        name_lower = (uploaded.name or "").lower()
        if not name_lower.endswith((".xlsx", ".xlsm")):
            return Response(
                {"detail": "Faqat .xlsx yoki .xlsm fayllar qabul qilinadi."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        column_targets = request.data.get("column_targets") or request.POST.get(
            "column_targets"
        )

        try:
            stats = import_products_from_excel(
                request.user.tenant,
                uploaded,
                column_targets=column_targets,
            )
        except Exception as exc:
            return Response(
                {"detail": f"Import xatosi: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(stats)

    @action(
        detail=True,
        methods=["post"],
        url_path="images",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_images(self, request, pk=None):
        product = self.get_object()
        files = request.FILES.getlist("images")
        if not files:
            single = request.FILES.get("image")
            if single:
                files = [single]
        if not files:
            return Response({"detail": "Rasm fayli yuklang."}, status=status.HTTP_400_BAD_REQUEST)

        created = []
        for file in files:
            row = attach_product_image(
                product,
                file,
                is_primary=product.images.count() == 0 and len(created) == 0,
            )
            created.append(row)

        return Response(
            {
                "images": product_images_payload(product, request),
                "image_url": ProductSerializer(product, context={"request": request}).data.get(
                    "image_url"
                ),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"images/(?P<image_id>[^/.]+)",
    )
    def delete_image(self, request, pk=None, image_id=None):
        product = self.get_object()
        row = ProductImage.objects.filter(product=product, id=image_id).first()
        if not row:
            return Response({"detail": "Rasm topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        was_primary = row.is_primary
        row.image.delete(save=False)
        row.delete()

        if was_primary:
            next_row = product.images.order_by("sort_order", "created_at").first()
            if next_row:
                next_row.is_primary = True
                next_row.save(update_fields=["is_primary"])
                product.image = next_row.image
                product.save(update_fields=["image", "updated_at"])
            else:
                product.image = None
                product.save(update_fields=["image", "updated_at"])

        return Response(
            {
                "images": product_images_payload(product, request),
                "image_url": ProductSerializer(product, context={"request": request}).data.get(
                    "image_url"
                ),
            }
        )

    @action(
        detail=True,
        methods=["post"],
        url_path=r"images/(?P<image_id>[^/.]+)/primary",
    )
    def set_primary_image(self, request, pk=None, image_id=None):
        product = self.get_object()
        row = ProductImage.objects.filter(product=product, id=image_id).first()
        if not row:
            return Response({"detail": "Rasm topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        product.images.update(is_primary=False)
        row.is_primary = True
        row.save(update_fields=["is_primary"])
        if row.image and product.image != row.image:
            product.image = row.image
            product.save(update_fields=["image", "updated_at"])

        return Response(
            {
                "images": product_images_payload(product, request),
                "image_url": ProductSerializer(product, context={"request": request}).data.get(
                    "image_url"
                ),
            }
        )
