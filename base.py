"""
Store models for FreshCart.

Defines Store, StoreCategory, and OperatingHours models.
"""

import uuid

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class StoreCategory(models.Model):
    """Category types for stores (e.g., Supermarket, Organic, Specialty)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon class name or emoji for the category",
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "store category"
        verbose_name_plural = "store categories"
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class Store(models.Model):
    """
    Represents a grocery store on the platform.
    Each store is owned by a store owner user.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Approval"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        CLOSED = "closed", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stores",
        limit_choices_to={"role": "store_owner"},
    )
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        StoreCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stores",
    )

    # Contact information
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    # Address
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default="US")

    # Geolocation
    location = gis_models.PointField(
        geography=True,
        help_text="Store coordinates (longitude, latitude)",
    )

    # Delivery configuration
    delivery_radius_km = models.FloatField(
        default=10.0,
        validators=[MinValueValidator(1.0), MaxValueValidator(50.0)],
        help_text="Maximum delivery radius in kilometers",
    )
    minimum_order_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=10.00,
        help_text="Minimum order amount for delivery",
    )
    delivery_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=2.99,
    )
    free_delivery_threshold = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Order amount above which delivery is free",
    )

    # Media
    logo = models.ImageField(upload_to="store_logos/%Y/%m/", blank=True, null=True)
    banner = models.ImageField(upload_to="store_banners/%Y/%m/", blank=True, null=True)

    # Status and ratings
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    total_ratings = models.PositiveIntegerField(default=0)
    total_orders = models.PositiveIntegerField(default=0)

    # Preparation time
    average_prep_time_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Average order preparation time in minutes",
    )

    # Flags
    is_featured = models.BooleanField(default=False)
    accepts_online_payments = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "store"
        verbose_name_plural = "stores"
        ordering = ["-is_featured", "-rating"]
        indexes = [
            models.Index(fields=["status", "city"]),
            models.Index(fields=["-rating", "-total_orders"]),
        ]

    def __str__(self):
        return self.name

    @property
    def is_open(self):
        """Check if the store is currently open based on operating hours."""
        from django.utils import timezone

        now = timezone.localtime()
        current_day = now.strftime("%A").lower()
        current_time = now.time()

        hours = self.operating_hours.filter(
            day_of_week=current_day, is_closed=False
        ).first()
        if not hours:
            return False

        return hours.open_time <= current_time <= hours.close_time

    def update_rating(self, new_rating):
        """Update store rating using cumulative average."""
        if self.total_ratings == 0:
            self.rating = new_rating
        else:
            total = float(self.rating) * self.total_ratings + new_rating
            self.rating = round(total / (self.total_ratings + 1), 2)
        self.total_ratings += 1
        self.save(update_fields=["rating", "total_ratings"])

    def calculate_delivery_fee(self, distance_km):
        """Calculate delivery fee based on distance."""
        if (
            self.free_delivery_threshold
            and distance_km <= self.delivery_radius_km
        ):
            return self.delivery_fee
        fee_per_km = float(
            settings.FRESHCART.get("DELIVERY_FEE_PER_KM", 1.50)
        )
        base_fee = float(
            settings.FRESHCART.get("BASE_DELIVERY_FEE", 2.99)
        )
        return round(base_fee + (distance_km * fee_per_km), 2)


class OperatingHours(models.Model):
    """
    Operating hours for each day of the week for a store.
    """

    class DayOfWeek(models.TextChoices):
        MONDAY = "monday", "Monday"
        TUESDAY = "tuesday", "Tuesday"
        WEDNESDAY = "wednesday", "Wednesday"
        THURSDAY = "thursday", "Thursday"
        FRIDAY = "friday", "Friday"
        SATURDAY = "saturday", "Saturday"
        SUNDAY = "sunday", "Sunday"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="operating_hours",
    )
    day_of_week = models.CharField(
        max_length=10,
        choices=DayOfWeek.choices,
    )
    open_time = models.TimeField()
    close_time = models.TimeField()
    is_closed = models.BooleanField(
        default=False,
        help_text="Mark as closed for this day",
    )

    class Meta:
        verbose_name = "operating hours"
        verbose_name_plural = "operating hours"
        unique_together = ["store", "day_of_week"]
        ordering = [
            models.Case(
                models.When(day_of_week="monday", then=0),
                models.When(day_of_week="tuesday", then=1),
                models.When(day_of_week="wednesday", then=2),
                models.When(day_of_week="thursday", then=3),
                models.When(day_of_week="friday", then=4),
                models.When(day_of_week="saturday", then=5),
                models.When(day_of_week="sunday", then=6),
            )
        ]

    def __str__(self):
        if self.is_closed:
            return f"{self.store.name} - {self.get_day_of_week_display()}: Closed"
        return (
            f"{self.store.name} - {self.get_day_of_week_display()}: "
            f"{self.open_time.strftime('%H:%M')} - {self.close_time.strftime('%H:%M')}"
        )
