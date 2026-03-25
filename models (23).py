"""
Payment models for FreshCart.

Defines Payment, Refund, and PromoCode models for handling
transactions, refunds, and promotional discounts.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Payment(models.Model):
    """
    Represents a payment transaction for an order.
    Tracks the full lifecycle of a payment from creation to settlement.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        AUTHORIZED = "authorized", "Authorized"
        CAPTURED = "captured", "Captured"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"

    class Method(models.TextChoices):
        STRIPE = "stripe", "Stripe"
        CASH = "cash", "Cash on Delivery"
        WALLET = "wallet", "FreshCart Wallet"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payment",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
    )

    # Payment details
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
        default=Method.STRIPE,
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(max_length=3, default="USD")

    # Stripe-specific fields
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_charge_id = models.CharField(max_length=255, blank=True)
    stripe_client_secret = models.CharField(max_length=255, blank=True)

    # Card info (last 4 digits only, for display purposes)
    card_last_four = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=20, blank=True)

    # Metadata
    failure_reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    # Timestamps
    authorized_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "payment"
        verbose_name_plural = "payments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return (
            f"Payment {self.id} - Order {self.order.order_number} "
            f"({self.get_status_display()})"
        )

    def mark_authorized(self, payment_intent_id, charge_id=""):
        """Mark payment as authorized."""
        self.status = self.Status.AUTHORIZED
        self.stripe_payment_intent_id = payment_intent_id
        self.stripe_charge_id = charge_id
        self.authorized_at = timezone.now()
        self.save(update_fields=[
            "status", "stripe_payment_intent_id", "stripe_charge_id",
            "authorized_at", "updated_at",
        ])

    def mark_captured(self):
        """Mark payment as captured (funds collected)."""
        self.status = self.Status.CAPTURED
        self.captured_at = timezone.now()
        self.save(update_fields=["status", "captured_at", "updated_at"])

    def mark_failed(self, reason=""):
        """Mark payment as failed."""
        self.status = self.Status.FAILED
        self.failure_reason = reason
        self.failed_at = timezone.now()
        self.save(update_fields=[
            "status", "failure_reason", "failed_at", "updated_at",
        ])

    @property
    def is_refundable(self):
        return self.status in (self.Status.CAPTURED, self.Status.PARTIALLY_REFUNDED)

    @property
    def refunded_amount(self):
        return self.refunds.filter(
            status=Refund.Status.COMPLETED,
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

    @property
    def remaining_refundable(self):
        return self.amount - self.refunded_amount


class Refund(models.Model):
    """
    Represents a refund for a payment.
    Supports full and partial refunds.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class Reason(models.TextChoices):
        CUSTOMER_REQUEST = "customer_request", "Customer Request"
        ORDER_CANCELLED = "order_cancelled", "Order Cancelled"
        ITEM_UNAVAILABLE = "item_unavailable", "Item Unavailable"
        QUALITY_ISSUE = "quality_issue", "Quality Issue"
        WRONG_ITEM = "wrong_item", "Wrong Item Delivered"
        LATE_DELIVERY = "late_delivery", "Late Delivery"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="refunds",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reason = models.CharField(
        max_length=30,
        choices=Reason.choices,
        default=Reason.OTHER,
    )
    reason_detail = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    stripe_refund_id = models.CharField(max_length=255, blank=True)
    failure_reason = models.TextField(blank=True)

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_refunds",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "refund"
        verbose_name_plural = "refunds"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Refund ${self.amount} for Payment {self.payment.id} "
            f"({self.get_status_display()})"
        )

    def validate_amount(self):
        """Ensure refund amount does not exceed remaining refundable amount."""
        remaining = self.payment.remaining_refundable
        if self.amount > remaining:
            raise ValueError(
                f"Refund amount (${self.amount}) exceeds remaining "
                f"refundable amount (${remaining})."
            )


class PromoCode(models.Model):
    """
    Promotional codes for discounts on orders.
    Supports percentage and fixed amount discounts.
    """

    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed Amount"
        FREE_DELIVERY = "free_delivery", "Free Delivery"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.TextField(blank=True)

    discount_type = models.CharField(
        max_length=20,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE,
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Percentage (0-100) or fixed amount in dollars",
    )
    max_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum discount cap for percentage discounts",
    )
    minimum_order_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Minimum order subtotal required to use this code",
    )

    # Usage limits
    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total number of times this code can be used (null = unlimited)",
    )
    usage_limit_per_user = models.PositiveIntegerField(
        default=1,
        help_text="Number of times each user can use this code",
    )
    times_used = models.PositiveIntegerField(default=0)

    # Restrictions
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    first_order_only = models.BooleanField(
        default=False,
        help_text="Only applicable to users placing their first order",
    )

    # Store restriction (null = valid at all stores)
    applicable_stores = models.ManyToManyField(
        "stores.Store",
        blank=True,
        related_name="promo_codes",
        help_text="Leave empty to apply to all stores",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "promo code"
        verbose_name_plural = "promo codes"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} ({self.get_discount_type_display()}: {self.discount_value})"

    @property
    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if now < self.valid_from or now > self.valid_until:
            return False
        if self.usage_limit is not None and self.times_used >= self.usage_limit:
            return False
        return True

    def calculate_discount(self, subtotal):
        """Calculate the discount amount for a given subtotal."""
        if subtotal < self.minimum_order_amount:
            return Decimal("0.00")

        if self.discount_type == self.DiscountType.PERCENTAGE:
            discount = subtotal * (self.discount_value / 100)
            if self.max_discount_amount:
                discount = min(discount, self.max_discount_amount)
            return round(discount, 2)

        if self.discount_type == self.DiscountType.FIXED:
            return min(self.discount_value, subtotal)

        if self.discount_type == self.DiscountType.FREE_DELIVERY:
            return Decimal("0.00")  # Handled at order level

        return Decimal("0.00")

    def increment_usage(self):
        """Increment the usage counter."""
        self.times_used += 1
        self.save(update_fields=["times_used"])
