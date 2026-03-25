"""
Admin configuration for products app.
"""

from django.contrib import admin

from .models import Category, GroceryProduct, ProductImage, ProductReview, ProductVariant


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = [
        "name",
        "sku",
        "price",
        "compare_at_price",
        "stock_quantity",
        "weight",
        "is_available",
    ]


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ["image", "alt_text", "display_order", "is_primary"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slug",
        "parent",
        "is_active",
        "display_order",
    ]
    list_filter = ["is_active", "parent"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]
    ordering = ["display_order", "name"]


@admin.register(GroceryProduct)
class GroceryProductAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "store",
        "category",
        "price",
        "stock_quantity",
        "is_available",
        "is_featured",
        "rating",
        "total_sold",
    ]
    list_filter = [
        "is_available",
        "is_featured",
        "is_perishable",
        "category",
        "store",
        "unit",
    ]
    search_fields = ["name", "description", "sku", "brand"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = [
        "rating",
        "total_ratings",
        "total_sold",
        "created_at",
        "updated_at",
    ]
    inlines = [ProductVariantInline, ProductImageInline]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "store",
                    "name",
                    "slug",
                    "category",
                    "description",
                    "sku",
                )
            },
        ),
        (
            "Pricing",
            {
                "fields": (
                    "price",
                    "compare_at_price",
                    "unit",
                    "unit_quantity",
                )
            },
        ),
        (
            "Inventory",
            {
                "fields": (
                    "stock_quantity",
                    "low_stock_threshold",
                    "max_order_quantity",
                )
            },
        ),
        (
            "Media",
            {"fields": ("image", "thumbnail")},
        ),
        (
            "Attributes",
            {
                "fields": (
                    "brand",
                    "weight",
                    "dietary_tags",
                    "ingredients",
                    "nutritional_info",
                    "allergens",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_available",
                    "is_featured",
                    "is_perishable",
                )
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "rating",
                    "total_ratings",
                    "total_sold",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["mark_available", "mark_unavailable", "toggle_featured"]

    @admin.action(description="Mark selected products as available")
    def mark_available(self, request, queryset):
        queryset.update(is_available=True)

    @admin.action(description="Mark selected products as unavailable")
    def mark_unavailable(self, request, queryset):
        queryset.update(is_available=False)

    @admin.action(description="Toggle featured status")
    def toggle_featured(self, request, queryset):
        for product in queryset:
            product.is_featured = not product.is_featured
            product.save(update_fields=["is_featured"])


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = [
        "product",
        "customer",
        "rating",
        "is_verified_purchase",
        "created_at",
    ]
    list_filter = ["rating", "is_verified_purchase", "created_at"]
    search_fields = ["product__name", "customer__email", "comment"]
    readonly_fields = ["created_at", "updated_at"]
