"""
Admin configuration for payments app.
"""

from django.contrib import admin

from .models import Payment, PromoCode, Refund


class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0
    readonly_fields = ["created_at", "completed_at"]
    fields = [
        "amount",
        "reason",
        "reason_detail",
        "status",
        "stripe_refund_id",
        "initiated_by",
        "created_at",
    ]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "order",
        "customer",
        "method",
        "status",
        "amount",
        "currency",
        "card_brand",
        "card_last_four",
        "created_at",
    ]
    list_filter = ["method", "status", "currency", "created_at"]
    search_fields = [
        "order__order_number",
        "customer__email",
        "stripe_payment_intent_id",
    ]
    readonly_fields = [
        "stripe_payment_intent_id",
        "stripe_charge_id",
        "stripe_client_secret",
        "authorized_at",
        "captured_at",
        "failed_at",
        "created_at",
        "updated_at",
    ]
    inlines = [RefundInline]

    fieldsets = (
        (
            None,
            {"fields": ("order", "customer", "method", "status", "amount", "currency")},
        ),
        (
            "Card Details",
            {"fields": ("card_last_four", "card_brand")},
        ),
        (
            "Stripe Details",
            {
                "fields": (
                    "stripe_payment_intent_id",
                    "stripe_charge_id",
                    "stripe_client_secret",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Failure Info",
            {"fields": ("failure_reason",), "classes": ("collapse",)},
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "authorized_at",
                    "captured_at",
                    "failed_at",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "payment",
        "amount",
        "reason",
        "status",
        "initiated_by",
        "created_at",
    ]
    list_filter = ["reason", "status", "created_at"]
    search_fields = [
        "payment__order__order_number",
        "stripe_refund_id",
    ]
    readonly_fields = ["created_at", "completed_at"]


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "discount_type",
        "discount_value",
        "times_used",
        "usage_limit",
        "valid_from",
        "valid_until",
        "is_active",
    ]
    list_filter = [
        "discount_type",
        "is_active",
        "first_order_only",
        "valid_from",
        "valid_until",
    ]
    search_fields = ["code", "description"]
    readonly_fields = ["times_used", "created_at", "updated_at"]
    filter_horizontal = ["applicable_stores"]

    fieldsets = (
        (None, {"fields": ("code", "description")}),
        (
            "Discount",
            {
                "fields": (
                    "discount_type",
                    "discount_value",
                    "max_discount_amount",
                    "minimum_order_amount",
                )
            },
        ),
        (
            "Usage Limits",
            {
                "fields": (
                    "usage_limit",
                    "usage_limit_per_user",
                    "times_used",
                )
            },
        ),
        (
            "Validity",
            {"fields": ("valid_from", "valid_until", "is_active", "first_order_only")},
        ),
        (
            "Restrictions",
            {"fields": ("applicable_stores",)},
        ),
        (
            "Meta",
            {
                "fields": ("created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
