"""
Account views for FreshCart.

Handles user registration, authentication, profile management,
and admin user operations.
"""

import logging

from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import CustomerProfile, DeliveryAddress, DriverProfile, StoreOwnerProfile
from .permissions import IsAdmin, IsCustomer, IsDriver, IsOwnerOrAdmin, IsStoreOwner
from .serializers import (
    AdminUserSerializer,
    ChangePasswordSerializer,
    CustomerProfileSerializer,
    DeliveryAddressSerializer,
    DriverProfileSerializer,
    CustomTokenObtainPairSerializer,
    StoreOwnerProfileSerializer,
    UserProfileUpdateSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom JWT token view that returns user data alongside tokens."""

    serializer_class = CustomTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    """Register a new user account."""

    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        logger.info(f"New user registered: {user.email} (role: {user.role})")
        return Response(
            {
                "message": "Registration successful.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ProfileView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or update the authenticated user's profile.
    Returns the appropriate profile data based on user role.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return UserProfileUpdateSerializer
        return UserSerializer

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        user = self.get_object()
        data = UserSerializer(user).data

        # Attach role-specific profile data
        if user.is_customer and hasattr(user, "customer_profile"):
            data["profile"] = CustomerProfileSerializer(
                user.customer_profile
            ).data
        elif user.is_store_owner and hasattr(user, "store_owner_profile"):
            data["profile"] = StoreOwnerProfileSerializer(
                user.store_owner_profile
            ).data
        elif user.is_driver and hasattr(user, "driver_profile"):
            data["profile"] = DriverProfileSerializer(
                user.driver_profile
            ).data

        return Response(data)


class ChangePasswordView(generics.UpdateAPIView):
    """Change the authenticated user's password."""

    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        logger.info(f"Password changed for user: {request.user.email}")
        return Response(
            {"message": "Password updated successfully."},
            status=status.HTTP_200_OK,
        )


class DeliveryAddressViewSet(viewsets.ModelViewSet):
    """CRUD operations for customer delivery addresses."""

    serializer_class = DeliveryAddressSerializer
    permission_classes = [permissions.IsAuthenticated, IsCustomer]

    def get_queryset(self):
        return DeliveryAddress.objects.filter(
            customer=self.request.user.customer_profile
        )

    def perform_destroy(self, instance):
        logger.info(
            f"Delivery address deleted: {instance.label} "
            f"for user {self.request.user.email}"
        )
        instance.delete()


class CustomerProfileView(generics.RetrieveUpdateAPIView):
    """Retrieve or update customer profile."""

    serializer_class = CustomerProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsCustomer]

    def get_object(self):
        profile, _ = CustomerProfile.objects.get_or_create(
            user=self.request.user
        )
        return profile


class StoreOwnerProfileView(generics.RetrieveUpdateAPIView):
    """Retrieve or update store owner profile."""

    serializer_class = StoreOwnerProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwner]

    def get_object(self):
        return self.request.user.store_owner_profile


class DriverProfileView(generics.RetrieveUpdateAPIView):
    """Retrieve or update driver profile."""

    serializer_class = DriverProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsDriver]

    def get_object(self):
        return self.request.user.driver_profile


class DriverAvailabilityView(generics.UpdateAPIView):
    """Toggle driver availability status."""

    serializer_class = DriverProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsDriver]

    def get_object(self):
        return self.request.user.driver_profile

    def update(self, request, *args, **kwargs):
        profile = self.get_object()
        new_status = request.data.get("availability_status")

        if new_status not in dict(DriverProfile.AvailabilityStatus.choices):
            return Response(
                {"error": "Invalid availability status."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prevent going online if not verified
        if (
            new_status == DriverProfile.AvailabilityStatus.ONLINE
            and not profile.is_verified
        ):
            return Response(
                {"error": "Your account must be verified before going online."},
                status=status.HTTP_403_FORBIDDEN,
            )

        profile.availability_status = new_status
        profile.save(update_fields=["availability_status"])
        logger.info(
            f"Driver {request.user.email} status changed to {new_status}"
        )
        return Response(
            DriverProfileSerializer(profile).data,
            status=status.HTTP_200_OK,
        )


class AdminUserViewSet(viewsets.ModelViewSet):
    """
    Admin-only viewset for managing all users.
    Supports listing, filtering, and updating user accounts.
    """

    serializer_class = AdminUserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    queryset = User.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["role", "is_active", "is_verified"]

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Verify a store owner or driver account."""
        user = self.get_object()
        if user.is_store_owner and hasattr(user, "store_owner_profile"):
            from django.utils import timezone

            user.store_owner_profile.is_verified = True
            user.store_owner_profile.verification_date = timezone.now()
            user.store_owner_profile.save()
        elif user.is_driver and hasattr(user, "driver_profile"):
            from django.utils import timezone

            user.driver_profile.is_verified = True
            user.driver_profile.verification_date = timezone.now()
            user.driver_profile.save()
        else:
            return Response(
                {"error": "User does not require verification."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_verified = True
        user.save(update_fields=["is_verified"])
        logger.info(f"User verified by admin: {user.email}")
        return Response(
            {"message": f"User {user.email} has been verified."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        """Suspend a user account."""
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        logger.info(f"User suspended by admin: {user.email}")
        return Response(
            {"message": f"User {user.email} has been suspended."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Reactivate a suspended user account."""
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        logger.info(f"User reactivated by admin: {user.email}")
        return Response(
            {"message": f"User {user.email} has been reactivated."},
            status=status.HTTP_200_OK,
        )
