"""
Account serializers for FreshCart.
"""

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    CustomerProfile,
    DeliveryAddress,
    DriverProfile,
    StoreOwnerProfile,
    User,
)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT token serializer that includes user role and profile info."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["email"] = user.email
        token["full_name"] = user.get_full_name()
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class UserSerializer(serializers.ModelSerializer):
    """Serializer for the User model."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "role",
            "avatar",
            "is_verified",
            "email_verified",
            "date_joined",
        ]
        read_only_fields = ["id", "email", "role", "is_verified", "date_joined"]


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        validators=[validate_password],
    )
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "password",
            "password_confirm",
        ]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        return value.lower()

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        # Restrict admin role registration
        if attrs.get("role") == User.Role.ADMIN:
            raise serializers.ValidationError(
                {"role": "Admin accounts cannot be created through registration."}
            )
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)

        # Create role-specific profile
        if user.role == User.Role.CUSTOMER:
            CustomerProfile.objects.create(user=user)
        elif user.role == User.Role.STORE_OWNER:
            StoreOwnerProfile.objects.create(
                user=user,
                business_name=f"{user.get_full_name()}'s Store",
            )
        elif user.role == User.Role.DRIVER:
            DriverProfile.objects.create(
                user=user,
                license_number="PENDING",
                license_expiry="2025-12-31",
            )

        return user


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "avatar"]


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change."""

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(
        required=True,
        min_length=8,
        validators=[validate_password],
    )
    new_password_confirm = serializers.CharField(required=True)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "New passwords do not match."}
            )
        return attrs


class DeliveryAddressSerializer(serializers.ModelSerializer):
    """Serializer for delivery addresses."""

    class Meta:
        model = DeliveryAddress
        fields = [
            "id",
            "label",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            "country",
            "instructions",
            "is_default",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        user = self.context["request"].user
        customer_profile = user.customer_profile
        validated_data["customer"] = customer_profile
        return super().create(validated_data)


class CustomerProfileSerializer(serializers.ModelSerializer):
    """Serializer for customer profiles."""

    user = UserSerializer(read_only=True)
    delivery_addresses = DeliveryAddressSerializer(many=True, read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "user",
            "default_delivery_address",
            "preferred_payment_method",
            "dietary_preferences",
            "loyalty_points",
            "total_orders",
            "total_spent",
            "delivery_addresses",
        ]
        read_only_fields = ["id", "loyalty_points", "total_orders", "total_spent"]


class StoreOwnerProfileSerializer(serializers.ModelSerializer):
    """Serializer for store owner profiles."""

    user = UserSerializer(read_only=True)

    class Meta:
        model = StoreOwnerProfile
        fields = [
            "id",
            "user",
            "business_name",
            "business_registration_number",
            "tax_id",
            "is_verified",
            "verification_date",
            "payout_method",
            "total_revenue",
        ]
        read_only_fields = [
            "id",
            "is_verified",
            "verification_date",
            "total_revenue",
        ]


class DriverProfileSerializer(serializers.ModelSerializer):
    """Serializer for driver profiles."""

    user = UserSerializer(read_only=True)

    class Meta:
        model = DriverProfile
        fields = [
            "id",
            "user",
            "vehicle_type",
            "vehicle_plate",
            "license_number",
            "license_expiry",
            "is_verified",
            "availability_status",
            "rating",
            "total_deliveries",
            "total_earnings",
            "average_delivery_time_minutes",
        ]
        read_only_fields = [
            "id",
            "is_verified",
            "rating",
            "total_deliveries",
            "total_earnings",
            "average_delivery_time_minutes",
        ]


class AdminUserSerializer(serializers.ModelSerializer):
    """Admin serializer with full user details and profile data."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)
    customer_profile = CustomerProfileSerializer(read_only=True)
    store_owner_profile = StoreOwnerProfileSerializer(read_only=True)
    driver_profile = DriverProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "role",
            "avatar",
            "is_active",
            "is_verified",
            "email_verified",
            "date_joined",
            "updated_at",
            "customer_profile",
            "store_owner_profile",
            "driver_profile",
        ]
        read_only_fields = ["id", "date_joined", "updated_at"]
