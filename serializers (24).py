"""
Payment serializers for FreshCart.
"""

from decimal import Decimal

from rest_framework import serializers

from .models import Payment, PromoCode, Refund


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for payment details."""

    order_number = serializers.CharField(source="order.order_number", read_only=True)
    customer_email = serializers.CharField(source="customer.email", read_only=True)
    refunded_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "order",
            "order_number",
            "customer",
            "customer_email",
            "method",
            "status",
            "amount",
            "currency",
            "card_last_four",
            "card_brand",
            "refunded_amount",
            "failure_reason",
            "authorized_at",
            "captured_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "card_last_four",
            "card_brand",
            "authorized_at",
            "captured_at",
            "created_at",
        ]


class PaymentIntentSerializer(serializers.Serializer):
    """Serializer for creating a payment intent."""

    order_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(
        choices=Payment.Method.choices,
        default=Payment.Method.STRIPE,
    )


class PaymentConfirmSerializer(serializers.Serializer):
    """Serializer for confirming a payment (webhook data)."""

    payment_intent_id = serializers.CharField()


class RefundSerializer(serializers.ModelSerializer):
    """Serializer for refund details."""

    initiated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Refund
        fields = [
            "id",
            "payment",
            "amount",
            "reason",
            "reason_detail",
            "status",
            "stripe_refund_id",
            "failure_reason",
            "initiated_by",
            "initiated_by_name",
            "created_at",
            "completed_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "stripe_refund_id",
            "failure_reason",
            "created_at",
            "completed_at",
        ]

    def get_initiated_by_name(self, obj):
        if obj.initiated_by:
            return obj.initiated_by.get_full_name()
        return None


class RefundCreateSerializer(serializers.Serializer):
    """Serializer for creating a refund."""

    order_id = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    reason = serializers.ChoiceField(choices=Refund.Reason.choices)
    reason_detail = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Refund amount must be positive.")
        return value


class PromoCodeSerializer(serializers.ModelSerializer):
    """Serializer for promo codes."""

    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = PromoCode
        fields = [
            "id",
            "code",
            "description",
            "discount_type",
            "discount_value",
            "max_discount_amount",
            "minimum_order_amount",
            "usage_limit",
            "usage_limit_per_user",
            "times_used",
            "valid_from",
            "valid_until",
            "is_active",
            "first_order_only",
            "is_valid",
            "created_at",
        ]
        read_only_fields = ["id", "times_used", "created_at"]


class PromoCodeApplySerializer(serializers.Serializer):
    """Serializer for applying a promo code to an order."""

    code = serializers.CharField(max_length=50)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    store_id = serializers.UUIDField(required=False)

    def validate_code(self, value):
        try:
            promo = PromoCode.objects.get(code__iexact=value)
        except PromoCode.DoesNotExist:
            raise serializers.ValidationError("Invalid promo code.")

        if not promo.is_valid:
            raise serializers.ValidationError("This promo code is no longer valid.")

        return value.upper()
