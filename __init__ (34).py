"""
Admin configuration for stores app.
"""

from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import OperatingHours, Store, StoreCategory


class OperatingHoursInline(admin.TabularInline):
    model = OperatingHours
    extra = 0
    fields = ["day_of_week", "open_time", "close_time", "is_closed"]


@admin.register(StoreCategory)
class StoreCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "icon", "is_active", "display_order"]
    list_filter = ["is_active"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]
    ordering = ["display_order", "name"]


@admin.register(Store)
class StoreAdmin(GISModelAdmin):
    list_display = [
        "name",
        "owner",
        "category",
        "city",
        "status",
        "rating",
        "total_orders",
        "is_featured",
        "created_at",
    ]
    list_filter = [
        "status",
        "category",
        "city",
        "is_featured",
        "accepts_online_payments",
    ]
    search_fields = ["name", "owner__email", "city", "description"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = [
        "rating",
        "total_ratings",
        "total_orders",
        "created_at",
        "updated_at",
    ]
    inlines = [OperatingHoursInline]

    fieldsets = (
        (None, {"fields": ("name", "slug", "owner", "category", "description")}),
        (
            "Contact",
            {"fields": ("phone", "email", "website")},
        ),
        (
            "Location",
            {
                "fields": (
                    "address_line_1",
                    "address_line_2",
                    "city",
                    "state",
                    "postal_code",
                    "country",
                    "location",
                )
            },
        ),
        (
            "Delivery Settings",
            {
                "fields": (
                    "delivery_radius_km",
                    "minimum_order_amount",
                    "delivery_fee",
                    "free_delivery_threshold",
                    "average_prep_time_minutes",
                )
            },
        ),
        (
            "Media",
            {"fields": ("logo", "banner")},
        ),
        (
            "Status & Ratings",
            {
                "fields": (
                    "status",
                    "rating",
                    "total_ratings",
                    "total_orders",
                    "is_featured",
                    "accepts_online_payments",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["approve_stores", "suspend_stores", "feature_stores"]

    @admin.action(description="Approve selected stores")
    def approve_stores(self, request, queryset):
        updated = queryset.filter(status=Store.Status.PENDING).update(
            status=Store.Status.ACTIVE
        )
        self.message_user(request, f"{updated} store(s) approved.")

    @admin.action(description="Suspend selected stores")
    def suspend_stores(self, request, queryset):
        updated = queryset.update(status=Store.Status.SUSPENDED)
        self.message_user(request, f"{updated} store(s) suspended.")

    @admin.action(description="Toggle featured status")
    def feature_stores(self, request, queryset):
        for store in queryset:
            store.is_featured = not store.is_featured
            store.save(update_fields=["is_featured"])
        self.message_user(request, "Featured status toggled.")


@admin.register(OperatingHours)
class OperatingHoursAdmin(admin.ModelAdmin):
    list_display = ["store", "day_of_week", "open_time", "close_time", "is_closed"]
    list_filter = ["day_of_week", "is_closed"]
    search_fields = ["store__name"]
