import uuid

from django.db import models

from apps.accounts.models import Tenant


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=200)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Kategoriyalar"
        ordering = ["sort_order", "name"]
        unique_together = [("tenant", "name")]

    def __str__(self):
        return self.name


class Brand(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="brands")
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("tenant", "name")]
        verbose_name = "Brend"
        verbose_name_plural = "Brendlar"

    def __str__(self):
        return self.name


class Supplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="suppliers")
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UnitOfMeasure(models.Model):
    """O'lchov birligi — tortiladigan (kg) yoki dona."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="units")
    name = models.CharField(max_length=50)
    is_weighable = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("tenant", "name")]
        verbose_name = "O'lchov birligi"
        verbose_name_plural = "O'lchov birliklari"

    def __str__(self):
        return self.name


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=300)
    barcode = models.CharField(max_length=64, blank=True, db_index=True)
    sku = models.CharField(max_length=64, blank=True)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit = models.CharField(max_length=20, default="dona")
    unit_ref = models.ForeignKey(
        UnitOfMeasure,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
    )
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    brand = models.ForeignKey(
        Brand, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    image = models.ImageField(upload_to="products/%Y/%m/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["tenant", "barcode"]),
            models.Index(fields=["tenant", "name"]),
        ]

    def __str__(self):
        return self.name

    def sync_primary_barcode(self):
        first = self.barcodes.order_by("created_at").values_list("code", flat=True).first()
        primary = first or ""
        if self.barcode != primary:
            self.barcode = primary
            self.save(update_fields=["barcode", "updated_at"])


class ProductBarcode(models.Model):
    """Bitta mahsulotda cheksiz shtrix kod."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="product_barcodes")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="barcodes")
    code = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        unique_together = [("tenant", "code")]
        indexes = [models.Index(fields=["tenant", "code"])]

    def __str__(self):
        return self.code


class ProductImage(models.Model):
    """Mahsulot rasmlari — bitta mahsulotda cheksiz."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="product_images")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/%Y/%m/")
    sort_order = models.IntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at"]
        verbose_name = "Mahsulot rasmi"
        verbose_name_plural = "Mahsulot rasmlari"


class PriceList(models.Model):
    """Narxlar ro'yxati — kirim va sotuvda tanlanadi."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="price_lists")
    name = models.CharField(max_length=120)
    is_selling = models.BooleanField(
        default=False,
        help_text="Mahsulotning asosiy sotuv narxi (product.price)",
    )
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]
        unique_together = [("tenant", "name")]
        verbose_name = "Narxlar ro'yxati"
        verbose_name_plural = "Narxlar ro'yxatlari"

    def __str__(self):
        return self.name


class ProductPrice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="product_prices")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="list_prices")
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="product_prices")
    price = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = [("product", "price_list")]
        verbose_name = "Mahsulot narxi"
        verbose_name_plural = "Mahsulot narxlari"


class StockReceipt(models.Model):
    """Kirim qilish cheki."""

    STATUS_DRAFT = "draft"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Qoralama"),
        (STATUS_COMPLETED, "Yakunlangan"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="stock_receipts")
    user = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="stock_receipts"
    )
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="stock_receipts"
    )
    supplier_name = models.CharField(max_length=200, blank=True)
    warehouse = models.CharField(max_length=120, default="Asosiy")
    currency = models.CharField(max_length=10, default="SUM")
    receipt_number = models.PositiveIntegerField(default=0, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    price_list_ids = models.JSONField(default=list, blank=True)
    include_selling_price = models.BooleanField(default=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Kirim cheki"
        verbose_name_plural = "Kirim cheklari"


class StockReceiptItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt = models.ForeignKey(
        StockReceipt, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_receipt_items")
    product_name = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sale_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    list_prices = models.JSONField(default=dict, blank=True)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Kirim qatori"
        verbose_name_plural = "Kirim qatorlari"


class StockAudit(models.Model):
    """Reviziya cheki."""

    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [(STATUS_COMPLETED, "Yakunlangan")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="stock_audits")
    user = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="stock_audits"
    )
    warehouse = models.CharField(max_length=120, default="Asosiy")
    currency = models.CharField(max_length=10, default="SUM")
    audit_number = models.PositiveIntegerField(default=0, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    price_list_ids = models.JSONField(default=list, blank=True)
    include_selling_price = models.BooleanField(default=False)
    include_stock = models.BooleanField(default=True)
    include_cost_price = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Reviziya cheki"
        verbose_name_plural = "Reviziya cheklari"


class StockAuditItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audit = models.ForeignKey(StockAudit, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_audit_items")
    product_name = models.CharField(max_length=300)
    quantity_before = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    quantity_after = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    list_prices = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Reviziya qatori"
        verbose_name_plural = "Reviziya qatorlari"
