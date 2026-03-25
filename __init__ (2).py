"""
Custom permissions for FreshCart.

Provides role-based permission classes for controlling access
to API endpoints based on user roles.
"""

from rest_framework.permissions import BasePermission


class IsCustomer(BasePermission):
    """Allows access only to users with the Customer role."""

    message = "This action is restricted to customers."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_customer
        )


class IsStoreOwner(BasePermission):
    """Allows access only to users with the Store Owner role."""

    message = "This action is restricted to store owners."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_store_owner
        )


class IsDriver(BasePermission):
    """Allows access only to users with the Delivery Driver role."""

    message = "This action is restricted to delivery drivers."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_driver
        )


class IsAdmin(BasePermission):
    """Allows access only to admin users."""

    message = "This action is restricted to administrators."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (request.user.is_admin_user or request.user.is_superuser)
        )


class IsOwnerOrAdmin(BasePermission):
    """
    Allows access to the object owner or admin users.
    The object must have a `user` field or `owner` field.
    """

    message = "You do not have permission to access this resource."

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin_user or request.user.is_superuser:
            return True

        # Check for various owner field names
        if hasattr(obj, "user"):
            return obj.user == request.user
        if hasattr(obj, "owner"):
            return obj.owner == request.user
        if hasattr(obj, "customer"):
            return obj.customer.user == request.user

        return False


class IsStoreOwnerOfStore(BasePermission):
    """
    Allows access only if the user is the owner of the store
    associated with the object.
    """

    message = "You can only manage your own store's resources."

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin_user or request.user.is_superuser:
            return True

        # The object might be a Store or have a `store` field
        store = getattr(obj, "store", obj)
        return store.owner == request.user


class IsCustomerOrReadOnly(BasePermission):
    """
    Allows read access to anyone, write access only to customers.
    """

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_customer
        )


class IsVerifiedDriver(BasePermission):
    """Allows access only to verified delivery drivers."""

    message = "Your driver account must be verified to perform this action."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and request.user.is_driver):
            return False
        return (
            hasattr(request.user, "driver_profile")
            and request.user.driver_profile.is_verified
        )


class IsVerifiedStoreOwner(BasePermission):
    """Allows access only to verified store owners."""

    message = "Your store owner account must be verified to perform this action."

    def has_permission(self, request, view):
        if not (
            request.user
            and request.user.is_authenticated
            and request.user.is_store_owner
        ):
            return False
        return (
            hasattr(request.user, "store_owner_profile")
            and request.user.store_owner_profile.is_verified
        )
