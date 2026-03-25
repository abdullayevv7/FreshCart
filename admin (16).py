"""
Order models for FreshCart.

Defines Order, OrderItem, and DeliveryTracking models.
"""

import uuid

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.core.validators import MinValueValidator
from django.db import models


class Order(models.Model):
    """
    Represents a customer order from a specific store.
    Tracks the entire order lifecycle from placement to delivery.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready for Pickup"
        PICKED_UP = "picked_up", "Picked Up"
        EN_ROUTE = "en_route", "En Route"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        AUTHORIZED = "authorized", "Authorized"
        CAPTURED = "captured", "Captured"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    # Valid status transitions
    VALID_TRANSITIONS = {
        Status.PENDING: [Status.CONFIRMED, Status.CANCELLED],
        Status.CONFIRMED: [Status.PREPARING, Status.CANCELLED],
        Status.PREPARING: [Status.READY, Status.CANCELLED],
        Status.READY: [Status.PICKED_UP, Status.CANCELLED],
        Status.PICKED_UP: [Status.EN_ROUTE],
        Status.EN_ROUTE: [Status.DELIVERED],
        Status.DELIVERED: [Status.REFUNDED],
        Status.CANCELLED: [],
        Status.REFUNDED: [],
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        related_name="orders",
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries",
        limit_choices_to={"role": "driver"},
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )

    # Pricing
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    delivery_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
    )
    service_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Platform commission",
    )
    tax_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
    )
    discount_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
    )
    tip_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    # Promo code
    promo_code = models.CharField(max_length=50, blank=True)

    # Delivery information
    delivery_address = models.TextField()
    delivery_location = gis_models.PointField(
        geography=True,
        null=True,
        blank=True,
    )
    delivery_instructions = models.TextField(blank=True)
    estimated_delivery_time = models.DateTimeField(null=True, blank=True)
    actual_delivery_time = models.DateTimeField(null=True, blank=True)

    # Distance
    delivery_distance_km = models.FloatField(
        null=True,
        blank=True,
        help_text="Calculated distance from store to delivery address",
    )

    # Payment
    payment_intent_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Stripe payment intent ID",
    )

    # Customer feedback
    customer_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    customer_feedback = models.TextField(blank=True)
    driver_rating = models.PositiveSmallIntegerField(null=True, blank=True)

    # Notes
    store_notes = models.TextField(
        blank=True,
        help_text="Notes from store owner",
    )
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("customer", "Customer"),
            ("store", "Store"),
            ("driver", "Driver"),
            ("system", "System"),
        ],
    )

    # Timestamps
    confirmed_at = models.DateTimeField(null=True, blank=True)
    prepared_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "order"
        verbose_name_plural = "orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["store", "status"]),
            models.Index(fields=["driver", "status"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"Order #{self.order_number}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    def _generate_order_number(self):
        """Generate a unique order number."""
        import random
        import string
        from django.utils import timezone

        date_str = timezone.now().strftime("%Y%m%d")
        random_str = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"FC-{date_str}-{random_str}"

    def can_transition_to(self, new_status):
        """Check if the order can transition to the given status."""
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def transition_to(self, new_status, **kwargs):
        """
        Transition the order to a new status.
        Raises ValueError if the transition is not valid.
        """
        from django.utils import timezone

        if not self.can_transition_to(new_status):
            raise ValueError(
                f"Cannot transition from '{self.status}' to '{new_status}'."
            )

        self.status = new_status
        now = timezone.now()

        # Set timestamps based on status
        timestamp_map = {
            self.Status.CONFIRMED: "confirmed_at",
            self.Status.READY: "prepared_at",
            self.Status.PICKED_UP: "picked_up_at",
            self.Status.DELIVERED: "delivered_at",
            self.Status.CANCELLED: "cancelled_at",
        }

        if new_status in timestamp_map:
            setattr(self, timestamp_map[new_status], now)

        if new_status == self.Status.DELIVERED:
            self.actual_delivery_time = now

        # Handle cancellation details
        if new_status == self.Status.CANCELLED:
            self.cancellation_reason = kwargs.get("reason", "")
            self.cancelled_by = kwargs.get("cancelled_by", "system")

        self.save()
        return self

    def calculate_totals(self):
        """Recalculate order totals from items."""
        from decimal import Decimal

        items = self.items.all()
        self.subtotal = sum(
            item.quantity * item.unit_price for item in items
        )

        # Service fee (platform commission)
        commission_rate = Decimal(
            str(settings.FRESHCART.get("PLATFORM_COMMISSION_PERCENT", 12))
        ) / 100
        self.service_fee = round(self.subtotal * commission_rate, 2)

        # Tax (simplified - would be based on jurisdiction in production)
        tax_rate = Decimal("0.08")  # 8% tax
        self.tax_amount = round(self.subtotal * tax_rate, 2)

        # Total
        self.total_amount = (
            self.subtotal
            + self.delivery_fee
            + self.service_fee
            + self.tax_amount
            + self.tip_amount
            - self.discount_amount
        )
        self.save(
            update_fields=[
                "subtotal",
                "service_fee",
                "tax_amount",
                "total_amount",
            ]
        )

    @property
    def item_count(self):
        return self.items.aggregate(total=models.Sum("quantity"))["total"] or 0


class OrderItem(models.Model):
    """Individual items within an order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "products.GroceryProduct",
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_items",
    )
    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    # Snapshot of product at time of order (prices may change)
    product_name = models.CharField(max_length=255)
    product_image = models.URLField(blank=True)
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    quantity = models.PositiveIntegerField(default=1)

    # Computed
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    # Special requests
    notes = models.TextField(
        blank=True,
        help_text="Special instructions for this item",
    )

    # Substitution
    is_substitutable = models.BooleanField(
        default=True,
        help_text="Allow store to substitute if unavailable",
    )
    substituted_product = models.ForeignKey(
        "products.GroceryProduct",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="substitution_items",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "order item"
        verbose_name_plural = "order items"

    def __str__(self):
        return f"{self.quantity}x {self.product_name}"

    def save(self, *args, **kwargs):
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)


class DeliveryTracking(models.Model):
    """
    Tracks delivery status events and location updates for an order.
    Provides an audit trail of the delivery process.
    """

    class EventType(models.TextChoices):
        STATUS_CHANGE = "status_change", "Status Change"
        LOCATION_UPDATE = "location_update", "Location Update"
        DRIVER_ASSIGNED = "driver_assigned", "Driver Assigned"
        NOTE = "note", "Note"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="tracking_events",
    )
    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=Order.Status.choices,
        blank=True,
    )
    location = gis_models.PointField(
        geography=True,
        null=True,
        blank=True,
    )
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "delivery tracking"
        verbose_name_plural = "delivery tracking events"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Order #{self.order.order_number} - "
            f"{self.get_event_type_display()} at {self.created_at}"
        )
