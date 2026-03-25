"""
Product models for FreshCart.

Defines Category, GroceryProduct, ProductVariant, and ProductImage models.
"""

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Category(models.Model):
    """Product category hierarchy for grocery items."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(max_length=200, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="category_images/%Y/%m/", blank=True, null=True
    )
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "category"
        verbose_name_plural = "categories"
        ordering = ["display_order", "name"]

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    @property
    def full_path(self):
        """Return the full category path (e.g., 'Fruits > Citrus')."""
        parts = [self.name]
        parent = self.parent
        while parent:
            parts.insert(0, parent.name)
            parent = parent.parent
        return " > ".join(parts)


class GroceryProduct(models.Model):
    """
    Represents a grocery product available for purchase.
    Products belong to a store and a category.
    """

    class Unit(models.TextChoices):
        PIECE = "piece", "Piece"
        KG = "kg", "Kilogram"
        G = "g", "Gram"
        LB = "lb", "Pound"
        OZ = "oz", "Ounce"
        LITER = "liter", "Liter"
        ML = "ml", "Milliliter"
        PACK = "pack", "Pack"
        DOZEN = "dozen", "Dozen"
        BUNCH = "bunch", "Bunch"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        related_name="products",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    sku = models.CharField(
        max_length=50,
        blank=True,
        help_text="Stock Keeping Unit",
    )

    # Pricing
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    compare_at_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original price before discount",
    )

    # Unit and quantity
    unit = models.CharField(
        max_length=10,
        choices=Unit.choices,
        default=Unit.PIECE,
    )
    unit_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=1.00,
        help_text="Quantity per unit (e.g., 500 for 500g)",
    )

    # Inventory
    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        help_text="Alert when stock falls below this level",
    )
    max_order_quantity = models.PositiveIntegerField(
        default=50,
        help_text="Maximum quantity per order",
    )

    # Images
    image = models.ImageField(
        upload_to="product_images/%Y/%m/", blank=True, null=True
    )
    thumbnail = models.ImageField(
        upload_to="product_thumbnails/%Y/%m/", blank=True, null=True
    )

    # Product attributes
    brand = models.CharField(max_length=100, blank=True)
    weight = models.CharField(max_length=50, blank=True, help_text="Display weight")
    dietary_tags = models.JSONField(
        default=list,
        blank=True,
        help_text="List of tags: organic, vegan, gluten-free, etc.",
    )
    ingredients = models.TextField(
        blank=True,
        help_text="Product ingredients list",
    )
    nutritional_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="Nutritional information (calories, protein, etc.)",
    )
    allergens = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allergens",
    )

    # Status
    is_available = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False)
    is_perishable = models.BooleanField(
        default=False,
        help_text="Whether the product needs refrigeration",
    )

    # Ratings
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    total_ratings = models.PositiveIntegerField(default=0)
    total_sold = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "grocery product"
        verbose_name_plural = "grocery products"
        ordering = ["-is_featured", "-created_at"]
        unique_together = ["store", "slug"]
        indexes = [
            models.Index(fields=["store", "is_available"]),
            models.Index(fields=["category", "is_available"]),
            models.Index(fields=["-total_sold"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.store.name}"

    @property
    def is_on_sale(self):
        return (
            self.compare_at_price is not None
            and self.compare_at_price > self.price
        )

    @property
    def discount_percentage(self):
        if not self.is_on_sale:
            return 0
        discount = (
            (self.compare_at_price - self.price) / self.compare_at_price * 100
        )
        return round(discount, 0)

    @property
    def is_in_stock(self):
        return self.stock_quantity > 0

    @property
    def is_low_stock(self):
        return 0 < self.stock_quantity <= self.low_stock_threshold

    def decrement_stock(self, quantity):
        """Decrease stock after order confirmation. Returns True if successful."""
        if self.stock_quantity >= quantity:
            self.stock_quantity -= quantity
            if self.stock_quantity == 0:
                self.is_available = False
            self.save(update_fields=["stock_quantity", "is_available"])
            return True
        return False

    def restore_stock(self, quantity):
        """Restore stock after order cancellation."""
        self.stock_quantity += quantity
        if not self.is_available and self.stock_quantity > 0:
            self.is_available = True
        self.save(update_fields=["stock_quantity", "is_available"])

    def update_rating(self, new_rating):
        """Update product rating."""
        if self.total_ratings == 0:
            self.rating = new_rating
        else:
            total = float(self.rating) * self.total_ratings + new_rating
            self.rating = round(total / (self.total_ratings + 1), 2)
        self.total_ratings += 1
        self.save(update_fields=["rating", "total_ratings"])


class ProductVariant(models.Model):
    """
    Variants of a product (e.g., size, weight options).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        GroceryProduct,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    name = models.CharField(
        max_length=100,
        help_text="Variant name (e.g., '500g', 'Large', 'Pack of 6')",
    )
    sku = models.CharField(max_length=50, blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    compare_at_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    stock_quantity = models.PositiveIntegerField(default=0)
    weight = models.CharField(max_length=50, blank=True)
    is_available = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "product variant"
        verbose_name_plural = "product variants"
        ordering = ["price"]

    def __str__(self):
        return f"{self.product.name} - {self.name}"


class ProductImage(models.Model):
    """Additional images for a product."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        GroceryProduct,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="product_images/%Y/%m/")
    alt_text = models.CharField(max_length=255, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "product image"
        verbose_name_plural = "product images"
        ordering = ["display_order"]

    def __str__(self):
        return f"Image for {self.product.name}"

    def save(self, *args, **kwargs):
        if self.is_primary:
            ProductImage.objects.filter(
                product=self.product, is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class ProductReview(models.Model):
    """Customer reviews for products."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        GroceryProduct,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=200, blank=True)
    comment = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "product review"
        verbose_name_plural = "product reviews"
        unique_together = ["product", "customer"]
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Review by {self.customer.get_full_name()} "
            f"for {self.product.name}: {self.rating}/5"
        )
