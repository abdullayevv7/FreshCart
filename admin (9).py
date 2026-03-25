"""
Delivery models for FreshCart.

Defines DeliveryZone and DriverLocation models for managing
delivery areas and real-time driver tracking.
"""

import uuid

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models


class DeliveryZone(models.Model):
    """
    Defines geographic delivery zones for the platform.
    Used to determine whether a location is serviceable
    and to set zone-specific delivery fees.
    """

    class ZoneType(models.TextChoices):
        STANDARD = "standard", "Standard"
        EXPRESS = "express", "Express"
        PREMIUM = "premium", "Premium"
        RESTRICTED = "restricted", "Restricted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    zone_type = models.CharField(
        max_length=20,
        choices=ZoneType.choices,
        default=ZoneType.STANDARD,
    )
    description = models.TextField(blank=True)

    # Geographic boundary of the zone
    boundary = gis_models.PolygonField(
        geography=True,
        help_text="Geographic boundary polygon for this delivery zone",
    )
    center = gis_models.PointField(
        geography=True,
        help_text="Center point of the delivery zone",
    )

    # Configuration
    base_delivery_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=2.99,
    )
    fee_per_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1.50,
    )
    minimum_order_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=10.00,
    )
    estimated_delivery_minutes = models.PositiveIntegerField(
        default=45,
        help_text="Estimated delivery time in minutes for this zone",
    )
    max_delivery_radius_km = models.FloatField(default=15.0)

    # Status
    is_active = models.BooleanField(default=True)
    is_surge_active = models.BooleanField(
        default=False,
        help_text="Enable surge pricing for high demand",
    )
    surge_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.00,
        help_text="Surge pricing multiplier (1.0 = no surge)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "delivery zone"
        verbose_name_plural = "delivery zones"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_zone_type_display()})"

    def contains_point(self, point):
        """Check if a geographic point is within this delivery zone."""
        return self.boundary.contains(point)

    def calculate_delivery_fee(self, distance_km):
        """Calculate delivery fee for a given distance within this zone."""
        fee = float(self.base_delivery_fee) + (distance_km * float(self.fee_per_km))
        if self.is_surge_active:
            fee *= float(self.surge_multiplier)
        return round(fee, 2)


class DriverLocation(models.Model):
    """
    Stores driver location history for analytics and tracking.
    Real-time locations are stored in Redis for performance.
    This table stores periodic snapshots for historical analysis.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="location_history",
        limit_choices_to={"role": "driver"},
    )
    location = gis_models.PointField(
        geography=True,
        help_text="Driver GPS coordinates",
    )
    heading = models.FloatField(
        null=True,
        blank=True,
        help_text="Direction of travel in degrees (0-360)",
    )
    speed_kmh = models.FloatField(
        null=True,
        blank=True,
        help_text="Speed in km/h",
    )
    accuracy_meters = models.FloatField(
        null=True,
        blank=True,
        help_text="GPS accuracy in meters",
    )
    altitude = models.FloatField(null=True, blank=True)
    battery_level = models.FloatField(
        null=True,
        blank=True,
        help_text="Device battery level (0-100)",
    )

    # Associated order (if on a delivery)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_locations",
    )

    is_active_delivery = models.BooleanField(
        default=False,
        help_text="Whether the driver is actively delivering",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "driver location"
        verbose_name_plural = "driver locations"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["driver", "-created_at"]),
            models.Index(fields=["order", "-created_at"]),
        ]

    def __str__(self):
        return (
            f"{self.driver.get_full_name()} at "
            f"({self.location.y:.6f}, {self.location.x:.6f}) "
            f"on {self.created_at}"
        )


class DeliveryAssignment(models.Model):
    """
    Tracks delivery assignment attempts for an order.
    Records which drivers were offered the delivery and their responses.
    """

    class ResponseStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="delivery_assignments",
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="delivery_assignments",
    )
    response_status = models.CharField(
        max_length=20,
        choices=ResponseStatus.choices,
        default=ResponseStatus.PENDING,
    )
    distance_to_store_km = models.FloatField(
        null=True,
        blank=True,
    )
    estimated_pickup_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    offered_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    expiry_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this assignment offer expires",
    )

    class Meta:
        verbose_name = "delivery assignment"
        verbose_name_plural = "delivery assignments"
        ordering = ["-offered_at"]

    def __str__(self):
        return (
            f"Assignment: Order {self.order.order_number} -> "
            f"{self.driver.get_full_name()} ({self.response_status})"
        )

    @property
    def is_expired(self):
        from django.utils import timezone

        if self.expiry_at and self.response_status == self.ResponseStatus.PENDING:
            return timezone.now() > self.expiry_at
        return False
