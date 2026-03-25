"""
Account models for FreshCart.

Defines the custom User model and role-specific profile models.
"""

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Custom manager for the User model with email-based authentication."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", User.Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model using email as the primary identifier.
    Supports four roles: Customer, Store Owner, Delivery Driver, Admin.
    """

    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        STORE_OWNER = "store_owner", "Store Owner"
        DRIVER = "driver", "Delivery Driver"
        ADMIN = "admin", "Admin"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        db_index=True,
    )
    avatar = models.ImageField(upload_to="avatars/%Y/%m/", blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_store_owner(self):
        return self.role == self.Role.STORE_OWNER

    @property
    def is_driver(self):
        return self.role == self.Role.DRIVER

    @property
    def is_admin_user(self):
        return self.role == self.Role.ADMIN


class CustomerProfile(models.Model):
    """
    Extended profile for customers.
    Stores delivery addresses and preferences.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    default_delivery_address = models.TextField(blank=True)
    default_delivery_location = gis_models.PointField(
        geography=True,
        null=True,
        blank=True,
        help_text="Default delivery coordinates (longitude, latitude)",
    )
    preferred_payment_method = models.CharField(max_length=50, blank=True)
    dietary_preferences = models.JSONField(
        default=list,
        blank=True,
        help_text="List of dietary preferences (e.g., vegan, gluten-free)",
    )
    loyalty_points = models.PositiveIntegerField(default=0)
    total_orders = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "customer profile"
        verbose_name_plural = "customer profiles"

    def __str__(self):
        return f"Customer: {self.user.get_full_name()}"

    def add_loyalty_points(self, amount):
        """Award loyalty points based on order amount. 1 point per dollar."""
        points = int(amount)
        self.loyalty_points += points
        self.save(update_fields=["loyalty_points"])
        return points


class DeliveryAddress(models.Model):
    """Saved delivery addresses for a customer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="delivery_addresses",
    )
    label = models.CharField(
        max_length=50,
        help_text="Label for this address (e.g., Home, Work)",
    )
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default="US")
    location = gis_models.PointField(
        geography=True,
        null=True,
        blank=True,
        help_text="Coordinates (longitude, latitude)",
    )
    instructions = models.TextField(
        blank=True,
        help_text="Special delivery instructions",
    )
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "delivery address"
        verbose_name_plural = "delivery addresses"
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.label}: {self.address_line_1}, {self.city}"

    def save(self, *args, **kwargs):
        # Ensure only one default address per customer
        if self.is_default:
            DeliveryAddress.objects.filter(
                customer=self.customer, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class StoreOwnerProfile(models.Model):
    """
    Extended profile for store owners.
    Contains business verification information.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="store_owner_profile",
    )
    business_name = models.CharField(max_length=255)
    business_registration_number = models.CharField(max_length=100, blank=True)
    tax_id = models.CharField(max_length=50, blank=True)
    is_verified = models.BooleanField(
        default=False,
        help_text="Verified by admin after document review",
    )
    verification_date = models.DateTimeField(null=True, blank=True)
    bank_account_number = models.CharField(max_length=100, blank=True)
    bank_routing_number = models.CharField(max_length=100, blank=True)
    payout_method = models.CharField(
        max_length=50,
        choices=[
            ("bank_transfer", "Bank Transfer"),
            ("stripe", "Stripe"),
        ],
        default="stripe",
    )
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "store owner profile"
        verbose_name_plural = "store owner profiles"

    def __str__(self):
        return f"Store Owner: {self.business_name}"


class DriverProfile(models.Model):
    """
    Extended profile for delivery drivers.
    Stores vehicle info, license, and availability.
    """

    class VehicleType(models.TextChoices):
        BICYCLE = "bicycle", "Bicycle"
        MOTORCYCLE = "motorcycle", "Motorcycle"
        CAR = "car", "Car"
        VAN = "van", "Van"

    class AvailabilityStatus(models.TextChoices):
        ONLINE = "online", "Online"
        OFFLINE = "offline", "Offline"
        ON_DELIVERY = "on_delivery", "On Delivery"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="driver_profile",
    )
    vehicle_type = models.CharField(
        max_length=20,
        choices=VehicleType.choices,
        default=VehicleType.CAR,
    )
    vehicle_plate = models.CharField(max_length=20, blank=True)
    license_number = models.CharField(max_length=50)
    license_expiry = models.DateField()
    license_photo = models.ImageField(
        upload_to="driver_licenses/%Y/%m/", blank=True, null=True
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Verified by admin after document review",
    )
    verification_date = models.DateTimeField(null=True, blank=True)
    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.OFFLINE,
        db_index=True,
    )
    current_location = gis_models.PointField(
        geography=True,
        null=True,
        blank=True,
        help_text="Current GPS coordinates",
    )
    rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=5.00
    )
    total_deliveries = models.PositiveIntegerField(default=0)
    total_earnings = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    average_delivery_time_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Running average of delivery times in minutes",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "driver profile"
        verbose_name_plural = "driver profiles"

    def __str__(self):
        return f"Driver: {self.user.get_full_name()} ({self.vehicle_type})"

    @property
    def is_available(self):
        return self.availability_status == self.AvailabilityStatus.ONLINE

    def update_rating(self, new_rating):
        """Update driver rating using a weighted average."""
        if self.total_deliveries == 0:
            self.rating = new_rating
        else:
            total = float(self.rating) * self.total_deliveries + new_rating
            self.rating = round(total / (self.total_deliveries + 1), 2)
        self.save(update_fields=["rating"])

    def complete_delivery(self, earnings, delivery_time_minutes):
        """Record a completed delivery."""
        self.total_deliveries += 1
        self.total_earnings += earnings
        # Update running average delivery time
        if self.average_delivery_time_minutes == 0:
            self.average_delivery_time_minutes = delivery_time_minutes
        else:
            total_time = (
                self.average_delivery_time_minutes * (self.total_deliveries - 1)
                + delivery_time_minutes
            )
            self.average_delivery_time_minutes = int(
                total_time / self.total_deliveries
            )
        self.availability_status = self.AvailabilityStatus.ONLINE
        self.save(
            update_fields=[
                "total_deliveries",
                "total_earnings",
                "average_delivery_time_minutes",
                "availability_status",
            ]
        )
