"""
Admin configuration for orders app.
"""

from django.contrib import admin

from .models import DeliveryTracking, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["total_price", "created_at"]
    fields = [
        "product",
        "product_name",
        "unit_price",
        "quantity",
        "total_price",
        "notes",
        "is_substitutable",
    ]


class DeliveryTrackingInline(admin.TabularInline):
    model = DeliveryTracking
    extra = 0
    readonly_fields = ["created_at", "created_by"]
    fields = [
        "event_type",
        "status",
        "description",
        "created_at",
        "created_by",
    ]
    ordering = ["-created_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "order_number",
        "customer",
        "store",
        "driver",
        "status",
        "payment_status",
        "total_amount",
        "created_at",
    ]
    list_filter = [
        "status",
        "payment_status",
        "created_at",
        "store",
    ]
    search_fields = [
        "order_number",
        "customer__email",
        "customer__first_name",
        "store__name",
        "driver__email",
    ]
    readonly_fields = [
        "order_number",
        "subtotal",
        "service_fee",
        "tax_amount",
        "total_amount",
        "delivery_distance_km",
        "confirmed_at",
        "prepared_at",
        "picked_up_at",
        "delivered_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    ]
    inlines = [OrderItemInline, DeliveryTrackingInline]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "order_number",
                    "customer",
                    "store",
                    "driver",
                    "status",
                    "payment_status",
                )
            },
        ),
        (
            "Pricing",
            {
                "fields": (
                    "subtotal",
                    "delivery_fee",
                    "service_fee",
                    "tax_amount",
                    "discount_amount",
                    "tip_amount",
                    "total_amount",
                    "promo_code",
                )
            },
        ),
        (
            "Delivery",
            {
                "fields": (
                    "delivery_address",
                    "delivery_instructions",
                    "delivery_distance_km",
                    "estimated_delivery_time",
                    "actual_delivery_time",
                )
            },
        ),
        (
            "Payment",
            {"fields": ("payment_intent_id",)},
        ),
        (
            "Feedback",
            {
                "fields": (
                    "customer_rating",
                    "customer_feedback",
                    "driver_rating",
                )
            },
        ),
        (
            "Notes & Cancellation",
            {
                "fields": (
                    "store_notes",
                    "cancellation_reason",
                    "cancelled_by",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "confirmed_at",
                    "prepared_at",
                    "picked_up_at",
                    "delivered_at",
                    "cancelled_at",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["mark_delivered", "mark_cancelled"]

    @admin.action(description="Mark selected orders as delivered")
    def mark_delivered(self, request, queryset):
        count = 0
        for order in queryset:
            try:
                order.transition_to(Order.Status.DELIVERED)
                count += 1
            except ValueError:
                pass
        self.message_user(request, f"{count} order(s) marked as delivered.")

    @admin.action(description="Cancel selected orders")
    def mark_cancelled(self, request, queryset):
        count = 0
        for order in queryset:
            try:
                order.transition_to(
                    Order.Status.CANCELLED,
                    reason="Cancelled by admin",
                    cancelled_by="system",
                )
                count += 1
            except ValueError:
                pass
        self.message_user(request, f"{count} order(s) cancelled.")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = [
        "order",
        "product_name",
        "unit_price",
        "quantity",
        "total_price",
    ]
    search_fields = ["order__order_number", "product_name"]
    readonly_fields = ["total_price", "created_at"]


@admin.register(DeliveryTracking)
class DeliveryTrackingAdmin(admin.ModelAdmin):
    list_display = [
        "order",
        "event_type",
        "status",
        "created_at",
        "created_by",
    ]
    list_filter = ["event_type", "status", "created_at"]
    search_fields = ["order__order_number"]
    readonly_fields = ["created_at"]
