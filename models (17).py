"""
Order serializers for FreshCart.
"""

from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from apps.products.models import GroceryProduct, ProductVariant
from apps.stores.models import Store

from .models import DeliveryTracking, Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    """Serializer for order items."""

    product_id = serializers.UUIDField(write_only=True, source="product.id", required=False)
    variant_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_id",
            "variant",
            "variant_id",
            "product_name",
            "product_image",
            "unit_price",
            "quantity",
            "total_price",
            "notes",
            "is_substitutable",
            "substituted_product",
        ]
        read_only_fields = [
            "id",
            "product_name",
            "product_image",
            "unit_price",
            "total_price",
        ]


class OrderItemCreateSerializer(serializers.Serializer):
    """Serializer for creating order items during order placement."""

    product_id = serializers.UUIDField()
    variant_id = serializers.UUIDField(required=False)
    quantity = serializers.IntegerField(min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    is_substitutable = serializers.BooleanField(default=True)


class DeliveryTrackingSerializer(serializers.ModelSerializer):
    """Serializer for delivery tracking events."""

    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True
    )

    class Meta:
        model = DeliveryTracking
        fields = [
            "id",
            "event_type",
            "status",
            "description",
            "metadata",
            "created_at",
            "created_by_name",
        ]
        read_only_fields = ["id", "created_at"]


class OrderListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for order listings."""

    store_name = serializers.CharField(source="store.name", read_only=True)
    customer_name = serializers.CharField(
        source="customer.get_full_name", read_only=True
    )
    driver_name = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "store",
            "store_name",
            "customer_name",
            "driver_name",
            "status",
            "payment_status",
            "subtotal",
            "total_amount",
            "item_count",
            "delivery_address",
            "estimated_delivery_time",
            "created_at",
        ]

    def get_driver_name(self, obj):
        if obj.driver:
            return obj.driver.get_full_name()
        return None


class OrderDetailSerializer(serializers.ModelSerializer):
    """Full order detail serializer."""

    items = OrderItemSerializer(many=True, read_only=True)
    tracking_events = DeliveryTrackingSerializer(many=True, read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    customer_name = serializers.CharField(
        source="customer.get_full_name", read_only=True
    )
    customer_email = serializers.CharField(
        source="customer.email", read_only=True
    )
    driver_name = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "customer",
            "customer_name",
            "customer_email",
            "store",
            "store_name",
            "driver",
            "driver_name",
            "status",
            "payment_status",
            "subtotal",
            "delivery_fee",
            "service_fee",
            "tax_amount",
            "discount_amount",
            "tip_amount",
            "total_amount",
            "promo_code",
            "delivery_address",
            "delivery_instructions",
            "delivery_distance_km",
            "estimated_delivery_time",
            "actual_delivery_time",
            "customer_rating",
            "customer_feedback",
            "driver_rating",
            "store_notes",
            "cancellation_reason",
            "cancelled_by",
            "confirmed_at",
            "prepared_at",
            "picked_up_at",
            "delivered_at",
            "cancelled_at",
            "created_at",
            "updated_at",
            "items",
            "tracking_events",
        ]

    def get_driver_name(self, obj):
        if obj.driver:
            return obj.driver.get_full_name()
        return None


class OrderCreateSerializer(serializers.Serializer):
    """Serializer for creating a new order."""

    store_id = serializers.UUIDField()
    items = OrderItemCreateSerializer(many=True)
    delivery_address = serializers.CharField()
    delivery_latitude = serializers.FloatField()
    delivery_longitude = serializers.FloatField()
    delivery_instructions = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    promo_code = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    tip_amount = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        required=False,
        default=0,
    )
    payment_method = serializers.ChoiceField(
        choices=["stripe", "cash"],
        default="stripe",
    )

    def validate_store_id(self, value):
        try:
            store = Store.objects.get(
                id=value, status=Store.Status.ACTIVE
            )
        except Store.DoesNotExist:
            raise serializers.ValidationError("Store not found or not active.")
        return value

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Order must contain at least one item.")
        return value

    def validate(self, attrs):
        """Validate items belong to the store and are available."""
        store_id = attrs["store_id"]
        items = attrs["items"]

        for item_data in items:
            try:
                product = GroceryProduct.objects.get(
                    id=item_data["product_id"],
                    store_id=store_id,
                    is_available=True,
                )
            except GroceryProduct.DoesNotExist:
                raise serializers.ValidationError(
                    f"Product {item_data['product_id']} not found or not available."
                )

            if product.stock_quantity < item_data["quantity"]:
                raise serializers.ValidationError(
                    f"Insufficient stock for {product.name}. "
                    f"Available: {product.stock_quantity}"
                )

            if item_data["quantity"] > product.max_order_quantity:
                raise serializers.ValidationError(
                    f"Maximum order quantity for {product.name} "
                    f"is {product.max_order_quantity}."
                )

        return attrs

    def create(self, validated_data):
        """Create the order with all items and calculate totals."""
        from django.contrib.gis.geos import Point

        user = self.context["request"].user
        store = Store.objects.get(id=validated_data["store_id"])
        items_data = validated_data["items"]

        delivery_location = Point(
            validated_data["delivery_longitude"],
            validated_data["delivery_latitude"],
            srid=4326,
        )

        # Calculate delivery distance
        from utils.geo import calculate_distance

        distance_km = calculate_distance(
            store.location, delivery_location
        )

        # Calculate delivery fee
        delivery_fee = store.calculate_delivery_fee(distance_km)

        # Check if within delivery radius
        if distance_km > store.delivery_radius_km:
            raise serializers.ValidationError(
                "Delivery address is outside the store's delivery zone."
            )

        order = Order.objects.create(
            customer=user,
            store=store,
            delivery_address=validated_data["delivery_address"],
            delivery_location=delivery_location,
            delivery_instructions=validated_data.get("delivery_instructions", ""),
            delivery_distance_km=distance_km,
            delivery_fee=delivery_fee,
            tip_amount=validated_data.get("tip_amount", 0),
            promo_code=validated_data.get("promo_code", ""),
        )

        # Create order items
        for item_data in items_data:
            product = GroceryProduct.objects.get(id=item_data["product_id"])
            variant = None
            price = product.price

            if "variant_id" in item_data:
                try:
                    variant = ProductVariant.objects.get(
                        id=item_data["variant_id"], product=product
                    )
                    price = variant.price
                except ProductVariant.DoesNotExist:
                    pass

            OrderItem.objects.create(
                order=order,
                product=product,
                variant=variant,
                product_name=product.name,
                product_image=product.image.url if product.image else "",
                unit_price=price,
                quantity=item_data["quantity"],
                notes=item_data.get("notes", ""),
                is_substitutable=item_data.get("is_substitutable", True),
            )

        # Calculate totals
        order.calculate_totals()

        # Check minimum order
        if order.subtotal < store.minimum_order_amount:
            order.delete()
            raise serializers.ValidationError(
                f"Minimum order amount is ${store.minimum_order_amount}."
            )

        # Create initial tracking event
        DeliveryTracking.objects.create(
            order=order,
            event_type=DeliveryTracking.EventType.STATUS_CHANGE,
            status=Order.Status.PENDING,
            description="Order placed successfully.",
            created_by=user,
        )

        return order


class OrderStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating order status."""

    status = serializers.ChoiceField(choices=Order.Status.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class OrderRatingSerializer(serializers.Serializer):
    """Serializer for rating an order."""

    customer_rating = serializers.IntegerField(min_value=1, max_value=5)
    customer_feedback = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    driver_rating = serializers.IntegerField(
        min_value=1, max_value=5, required=False
    )
