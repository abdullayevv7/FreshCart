"""
Product serializers for FreshCart.
"""

from rest_framework import serializers

from .models import Category, GroceryProduct, ProductImage, ProductReview, ProductVariant


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for product categories."""

    children = serializers.SerializerMethodField()
    full_path = serializers.CharField(read_only=True)
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "parent",
            "description",
            "image",
            "icon",
            "is_active",
            "display_order",
            "full_path",
            "product_count",
            "children",
        ]
        read_only_fields = ["id"]

    def get_children(self, obj):
        children = obj.children.filter(is_active=True)
        return CategorySerializer(children, many=True, context=self.context).data

    def get_product_count(self, obj):
        return obj.products.filter(is_available=True).count()


class CategoryListSerializer(serializers.ModelSerializer):
    """Lightweight category serializer for listings."""

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon", "image"]


class ProductVariantSerializer(serializers.ModelSerializer):
    """Serializer for product variants."""

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "name",
            "sku",
            "price",
            "compare_at_price",
            "stock_quantity",
            "weight",
            "is_available",
        ]
        read_only_fields = ["id"]


class ProductImageSerializer(serializers.ModelSerializer):
    """Serializer for product images."""

    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "display_order", "is_primary"]
        read_only_fields = ["id"]


class ProductReviewSerializer(serializers.ModelSerializer):
    """Serializer for product reviews."""

    customer_name = serializers.CharField(
        source="customer.get_full_name", read_only=True
    )

    class Meta:
        model = ProductReview
        fields = [
            "id",
            "customer_name",
            "rating",
            "title",
            "comment",
            "is_verified_purchase",
            "created_at",
        ]
        read_only_fields = ["id", "customer_name", "is_verified_purchase", "created_at"]


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product listings."""

    category_name = serializers.CharField(
        source="category.name", read_only=True
    )
    store_name = serializers.CharField(source="store.name", read_only=True)
    is_on_sale = serializers.BooleanField(read_only=True)
    discount_percentage = serializers.IntegerField(read_only=True)
    is_in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = GroceryProduct
        fields = [
            "id",
            "name",
            "slug",
            "store",
            "store_name",
            "category",
            "category_name",
            "price",
            "compare_at_price",
            "unit",
            "unit_quantity",
            "image",
            "thumbnail",
            "brand",
            "weight",
            "dietary_tags",
            "is_available",
            "is_featured",
            "is_on_sale",
            "discount_percentage",
            "is_in_stock",
            "rating",
            "total_ratings",
            "stock_quantity",
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    """Full product detail serializer."""

    category_name = serializers.CharField(
        source="category.name", read_only=True
    )
    category_path = serializers.CharField(
        source="category.full_path", read_only=True
    )
    store_name = serializers.CharField(source="store.name", read_only=True)
    store_slug = serializers.CharField(source="store.slug", read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = serializers.SerializerMethodField()
    is_on_sale = serializers.BooleanField(read_only=True)
    discount_percentage = serializers.IntegerField(read_only=True)
    is_in_stock = serializers.BooleanField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = GroceryProduct
        fields = [
            "id",
            "name",
            "slug",
            "store",
            "store_name",
            "store_slug",
            "category",
            "category_name",
            "category_path",
            "description",
            "sku",
            "price",
            "compare_at_price",
            "unit",
            "unit_quantity",
            "stock_quantity",
            "max_order_quantity",
            "image",
            "thumbnail",
            "brand",
            "weight",
            "dietary_tags",
            "ingredients",
            "nutritional_info",
            "allergens",
            "is_available",
            "is_featured",
            "is_perishable",
            "is_on_sale",
            "discount_percentage",
            "is_in_stock",
            "is_low_stock",
            "rating",
            "total_ratings",
            "total_sold",
            "variants",
            "images",
            "reviews",
            "created_at",
            "updated_at",
        ]

    def get_reviews(self, obj):
        recent_reviews = obj.reviews.all()[:5]
        return ProductReviewSerializer(recent_reviews, many=True).data


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating products."""

    variants_data = ProductVariantSerializer(many=True, required=False, write_only=True)

    class Meta:
        model = GroceryProduct
        fields = [
            "name",
            "slug",
            "category",
            "description",
            "sku",
            "price",
            "compare_at_price",
            "unit",
            "unit_quantity",
            "stock_quantity",
            "low_stock_threshold",
            "max_order_quantity",
            "image",
            "thumbnail",
            "brand",
            "weight",
            "dietary_tags",
            "ingredients",
            "nutritional_info",
            "allergens",
            "is_available",
            "is_featured",
            "is_perishable",
            "variants_data",
        ]

    def validate(self, attrs):
        if attrs.get("compare_at_price") and attrs.get("price"):
            if attrs["compare_at_price"] <= attrs["price"]:
                raise serializers.ValidationError(
                    {
                        "compare_at_price": (
                            "Compare-at price must be greater than the selling price."
                        )
                    }
                )
        return attrs

    def create(self, validated_data):
        variants_data = validated_data.pop("variants_data", [])
        product = GroceryProduct.objects.create(**validated_data)

        for variant_data in variants_data:
            ProductVariant.objects.create(product=product, **variant_data)

        return product

    def update(self, instance, validated_data):
        variants_data = validated_data.pop("variants_data", None)
        product = super().update(instance, validated_data)

        if variants_data is not None:
            # Remove old variants and create new ones
            product.variants.all().delete()
            for variant_data in variants_data:
                ProductVariant.objects.create(product=product, **variant_data)

        return product
