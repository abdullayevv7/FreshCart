"""
Delivery serializers for FreshCart.
"""

from rest_framework import serializers

from .models import DeliveryAssignment, DeliveryZone, DriverLocation


class DeliveryZoneSerializer(serializers.ModelSerializer):
    """Serializer for delivery zones."""

    class Meta:
        model = DeliveryZone
        fields = [
            "id",
            "name",
            "zone_type",
            "description",
            "base_delivery_fee",
            "fee_per_km",
            "minimum_order_amount",
            "estimated_delivery_minutes",
            "max_delivery_radius_km",
            "is_active",
            "is_surge_active",
            "surge_multiplier",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class DeliveryZoneCheckSerializer(serializers.Serializer):
    """Serializer for checking if an address is in a delivery zone."""

    latitude = serializers.FloatField()
    longitude = serializers.FloatField()


class DriverLocationSerializer(serializers.ModelSerializer):
    """Serializer for driver location updates."""

    driver_name = serializers.CharField(
        source="driver.get_full_name", read_only=True
    )
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()

    class Meta:
        model = DriverLocation
        fields = [
            "id",
            "driver",
            "driver_name",
            "latitude",
            "longitude",
            "heading",
            "speed_kmh",
            "accuracy_meters",
            "altitude",
            "battery_level",
            "order",
            "is_active_delivery",
            "created_at",
        ]
        read_only_fields = ["id", "driver", "created_at"]

    def get_latitude(self, obj):
        return obj.location.y if obj.location else None

    def get_longitude(self, obj):
        return obj.location.x if obj.location else None


class DriverLocationUpdateSerializer(serializers.Serializer):
    """Serializer for real-time driver location updates."""

    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    heading = serializers.FloatField(required=False)
    speed_kmh = serializers.FloatField(required=False)
    accuracy_meters = serializers.FloatField(required=False)
    altitude = serializers.FloatField(required=False)
    battery_level = serializers.FloatField(required=False)

    def validate_latitude(self, value):
        if not -90 <= value <= 90:
            raise serializers.ValidationError(
                "Latitude must be between -90 and 90."
            )
        return value

    def validate_longitude(self, value):
        if not -180 <= value <= 180:
            raise serializers.ValidationError(
                "Longitude must be between -180 and 180."
            )
        return value


class DeliveryAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for delivery assignments."""

    driver_name = serializers.CharField(
        source="driver.get_full_name", read_only=True
    )
    order_number = serializers.CharField(
        source="order.order_number", read_only=True
    )

    class Meta:
        model = DeliveryAssignment
        fields = [
            "id",
            "order",
            "order_number",
            "driver",
            "driver_name",
            "response_status",
            "distance_to_store_km",
            "estimated_pickup_minutes",
            "offered_at",
            "responded_at",
            "expiry_at",
        ]
        read_only_fields = [
            "id",
            "offered_at",
            "responded_at",
        ]


class ActiveDeliverySerializer(serializers.Serializer):
    """Serializer for active delivery details for drivers."""

    order_id = serializers.UUIDField()
    order_number = serializers.CharField()
    status = serializers.CharField()
    store_name = serializers.CharField()
    store_address = serializers.CharField()
    store_latitude = serializers.FloatField()
    store_longitude = serializers.FloatField()
    customer_name = serializers.CharField()
    delivery_address = serializers.CharField()
    delivery_latitude = serializers.FloatField()
    delivery_longitude = serializers.FloatField()
    delivery_instructions = serializers.CharField()
    delivery_fee = serializers.DecimalField(max_digits=8, decimal_places=2)
    tip_amount = serializers.DecimalField(max_digits=8, decimal_places=2)
    items_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
