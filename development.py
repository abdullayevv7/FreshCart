"""
Store serializers for FreshCart.
"""

from rest_framework import serializers

from .models import OperatingHours, Store, StoreCategory


class StoreCategorySerializer(serializers.ModelSerializer):
    """Serializer for store categories."""

    store_count = serializers.SerializerMethodField()

    class Meta:
        model = StoreCategory
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "is_active",
            "display_order",
            "store_count",
        ]
        read_only_fields = ["id"]

    def get_store_count(self, obj):
        return obj.stores.filter(status=Store.Status.ACTIVE).count()


class OperatingHoursSerializer(serializers.ModelSerializer):
    """Serializer for operating hours."""

    day_display = serializers.CharField(
        source="get_day_of_week_display", read_only=True
    )

    class Meta:
        model = OperatingHours
        fields = [
            "id",
            "day_of_week",
            "day_display",
            "open_time",
            "close_time",
            "is_closed",
        ]
        read_only_fields = ["id"]


class StoreListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for store listings."""

    category_name = serializers.CharField(
        source="category.name", read_only=True
    )
    owner_name = serializers.CharField(
        source="owner.get_full_name", read_only=True
    )
    is_open = serializers.BooleanField(read_only=True)
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "category",
            "category_name",
            "owner_name",
            "city",
            "state",
            "logo",
            "rating",
            "total_ratings",
            "total_orders",
            "delivery_fee",
            "minimum_order_amount",
            "free_delivery_threshold",
            "average_prep_time_minutes",
            "is_featured",
            "is_open",
            "distance_km",
            "status",
        ]

    def get_distance_km(self, obj):
        """Return distance if it was annotated on the queryset."""
        if hasattr(obj, "distance"):
            return round(obj.distance.km, 2)
        return None


class StoreDetailSerializer(serializers.ModelSerializer):
    """Full store detail serializer with operating hours."""

    category_name = serializers.CharField(
        source="category.name", read_only=True
    )
    owner_name = serializers.CharField(
        source="owner.get_full_name", read_only=True
    )
    operating_hours = OperatingHoursSerializer(many=True, read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "category",
            "category_name",
            "owner_name",
            "phone",
            "email",
            "website",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            "country",
            "delivery_radius_km",
            "minimum_order_amount",
            "delivery_fee",
            "free_delivery_threshold",
            "average_prep_time_minutes",
            "logo",
            "banner",
            "rating",
            "total_ratings",
            "total_orders",
            "is_featured",
            "is_open",
            "accepts_online_payments",
            "operating_hours",
            "product_count",
            "status",
            "created_at",
        ]

    def get_product_count(self, obj):
        return obj.products.filter(is_available=True).count()


class StoreCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating stores."""

    operating_hours_data = OperatingHoursSerializer(many=True, required=False, write_only=True)

    class Meta:
        model = Store
        fields = [
            "name",
            "slug",
            "description",
            "category",
            "phone",
            "email",
            "website",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            "country",
            "delivery_radius_km",
            "minimum_order_amount",
            "delivery_fee",
            "free_delivery_threshold",
            "average_prep_time_minutes",
            "logo",
            "banner",
            "accepts_online_payments",
            "operating_hours_data",
        ]

    def validate_slug(self, value):
        qs = Store.objects.filter(slug=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A store with this slug already exists.")
        return value

    def create(self, validated_data):
        hours_data = validated_data.pop("operating_hours_data", [])
        # Default location - would be geocoded from address in production
        from django.contrib.gis.geos import Point

        if "location" not in validated_data:
            validated_data["location"] = Point(0, 0)

        store = Store.objects.create(**validated_data)

        for hours in hours_data:
            OperatingHours.objects.create(store=store, **hours)

        return store

    def update(self, instance, validated_data):
        hours_data = validated_data.pop("operating_hours_data", None)
        store = super().update(instance, validated_data)

        if hours_data is not None:
            store.operating_hours.all().delete()
            for hours in hours_data:
                OperatingHours.objects.create(store=store, **hours)

        return store


class StoreAnalyticsSerializer(serializers.Serializer):
    """Serializer for store analytics data."""

    total_orders = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=14, decimal_places=2)
    average_order_value = serializers.DecimalField(max_digits=10, decimal_places=2)
    orders_today = serializers.IntegerField()
    revenue_today = serializers.DecimalField(max_digits=10, decimal_places=2)
    popular_products = serializers.ListField()
    orders_by_status = serializers.DictField()
    rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    total_ratings = serializers.IntegerField()
