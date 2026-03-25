"""
Admin configuration for accounts app.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    CustomerProfile,
    DeliveryAddress,
    DriverProfile,
    StoreOwnerProfile,
    User,
)


class CustomerProfileInline(admin.StackedInline):
    model = CustomerProfile
    can_delete = False
    verbose_name_plural = "Customer Profile"
    fk_name = "user"


class StoreOwnerProfileInline(admin.StackedInline):
    model = StoreOwnerProfile
    can_delete = False
    verbose_name_plural = "Store Owner Profile"
    fk_name = "user"


class DriverProfileInline(admin.StackedInline):
    model = DriverProfile
    can_delete = False
    verbose_name_plural = "Driver Profile"
    fk_name = "user"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        "email",
        "first_name",
        "last_name",
        "role",
        "is_active",
        "is_verified",
        "date_joined",
    ]
    list_filter = ["role", "is_active", "is_verified", "is_staff", "date_joined"]
    search_fields = ["email", "first_name", "last_name", "phone"]
    ordering = ["-date_joined"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal info",
            {"fields": ("first_name", "last_name", "phone", "avatar")},
        ),
        (
            "Role & Status",
            {"fields": ("role", "is_verified", "email_verified")},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "role",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    def get_inlines(self, request, obj=None):
        if obj is None:
            return []
        inlines = []
        if obj.role == User.Role.CUSTOMER:
            inlines.append(CustomerProfileInline)
        elif obj.role == User.Role.STORE_OWNER:
            inlines.append(StoreOwnerProfileInline)
        elif obj.role == User.Role.DRIVER:
            inlines.append(DriverProfileInline)
        return inlines


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "loyalty_points",
        "total_orders",
        "total_spent",
        "created_at",
    ]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    readonly_fields = ["total_orders", "total_spent", "created_at", "updated_at"]


@admin.register(DeliveryAddress)
class DeliveryAddressAdmin(admin.ModelAdmin):
    list_display = [
        "customer",
        "label",
        "address_line_1",
        "city",
        "state",
        "is_default",
    ]
    list_filter = ["is_default", "city", "state"]
    search_fields = [
        "customer__user__email",
        "address_line_1",
        "city",
    ]


@admin.register(StoreOwnerProfile)
class StoreOwnerProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "business_name",
        "is_verified",
        "total_revenue",
        "created_at",
    ]
    list_filter = ["is_verified", "payout_method"]
    search_fields = ["user__email", "business_name"]
    readonly_fields = ["total_revenue", "created_at", "updated_at"]

    actions = ["verify_owners"]

    @admin.action(description="Verify selected store owners")
    def verify_owners(self, request, queryset):
        from django.utils import timezone

        updated = queryset.filter(is_verified=False).update(
            is_verified=True, verification_date=timezone.now()
        )
        self.message_user(request, f"{updated} store owner(s) verified.")


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "vehicle_type",
        "availability_status",
        "is_verified",
        "rating",
        "total_deliveries",
    ]
    list_filter = [
        "vehicle_type",
        "availability_status",
        "is_verified",
    ]
    search_fields = ["user__email", "license_number", "vehicle_plate"]
    readonly_fields = [
        "total_deliveries",
        "total_earnings",
        "average_delivery_time_minutes",
        "created_at",
        "updated_at",
    ]

    actions = ["verify_drivers"]

    @admin.action(description="Verify selected drivers")
    def verify_drivers(self, request, queryset):
        from django.utils import timezone

        updated = queryset.filter(is_verified=False).update(
            is_verified=True, verification_date=timezone.now()
        )
        self.message_user(request, f"{updated} driver(s) verified.")
