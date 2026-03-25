"""
Admin configuration for delivery app.
"""

from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import DeliveryAssignment, DeliveryZone, DriverLocation


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(GISModelAdmin):
    list_display = [
        "name",
        "zone_type",
        "base_delivery_fee",
        "fee_per_km",
        "estimated_delivery_minutes",
        "is_active",
        "is_surge_active",
        "surge_multiplier",
    ]
    list_filter = ["zone_type", "is_active", "is_surge_active"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (None, {"fields": ("name", "zone_type", "description")}),
        (
            "Geography",
            {"fields": ("boundary", "center")},
        ),
        (
            "Pricing",
            {
                "fields": (
                    "base_delivery_fee",
                    "fee_per_km",
                    "minimum_order_amount",
                    "estimated_delivery_minutes",
                    "max_delivery_radius_km",
                )
            },
        ),
        (
            "Surge Pricing",
            {"fields": ("is_surge_active", "surge_multiplier")},
        ),
        (
            "Status",
            {"fields": ("is_active",)},
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["activate_surge", "deactivate_surge"]

    @admin.action(description="Activate surge pricing")
    def activate_surge(self, request, queryset):
        queryset.update(is_surge_active=True)
        self.message_user(request, f"Surge pricing activated for {queryset.count()} zone(s).")

    @admin.action(description="Deactivate surge pricing")
    def deactivate_surge(self, request, queryset):
        queryset.update(is_surge_active=False, surge_multiplier=1.00)
        self.message_user(request, f"Surge pricing deactivated for {queryset.count()} zone(s).")


@admin.register(DriverLocation)
class DriverLocationAdmin(admin.ModelAdmin):
    list_display = [
        "driver",
        "speed_kmh",
        "is_active_delivery",
        "order",
        "battery_level",
        "created_at",
    ]
    list_filter = ["is_active_delivery", "created_at"]
    search_fields = ["driver__email", "driver__first_name", "order__order_number"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False  # Location records are created programmatically


@admin.register(DeliveryAssignment)
class DeliveryAssignmentAdmin(admin.ModelAdmin):
    list_display = [
        "order",
        "driver",
        "response_status",
        "distance_to_store_km",
        "estimated_pickup_minutes",
        "offered_at",
        "responded_at",
    ]
    list_filter = ["response_status", "offered_at"]
    search_fields = [
        "order__order_number",
        "driver__email",
        "driver__first_name",
    ]
    readonly_fields = ["offered_at", "responded_at"]
