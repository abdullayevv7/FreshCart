"""
Payment views for FreshCart.

Handles payment intent creation, Stripe webhooks,
refund processing, and promo code management.
"""

import logging

import stripe
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from apps.accounts.permissions import IsAdmin, IsCustomer, IsStoreOwner
from apps.orders.models import Order

from .models import Payment, PromoCode, Refund
from .serializers import (
    PaymentIntentSerializer,
    PaymentSerializer,
    PromoCodeApplySerializer,
    PromoCodeSerializer,
    RefundCreateSerializer,
    RefundSerializer,
)
from .services import PaymentService

logger = logging.getLogger(__name__)


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for viewing payment history.
    Customers see their own payments; admins see all.
    """

    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Payment.objects.select_related("order", "customer")

        if user.is_admin_user or user.is_superuser:
            return qs

        if user.is_store_owner:
            return qs.filter(order__store__owner=user)

        return qs.filter(customer=user)

    @action(detail=False, methods=["post"], url_path="create-intent")
    def create_intent(self, request):
        """
        Create a Stripe PaymentIntent for an order.

        POST body:
        - order_id: UUID of the order
        - payment_method: 'stripe' or 'cash'
        """
        serializer = PaymentIntentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order_id = serializer.validated_data["order_id"]
        payment_method = serializer.validated_data["payment_method"]

        try:
            order = Order.objects.get(
                id=order_id,
                customer=request.user,
                status=Order.Status.PENDING,
            )
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found or not eligible for payment."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if payment already exists
        if hasattr(order, "payment"):
            return Response(
                {
                    "error": "Payment already exists for this order.",
                    "payment_id": str(order.payment.id),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = PaymentService()

        if payment_method == Payment.Method.CASH:
            payment = service.create_cash_payment(order)
            return Response(
                {
                    "payment_id": str(payment.id),
                    "method": "cash",
                    "message": "Cash on delivery payment created.",
                },
                status=status.HTTP_201_CREATED,
            )

        try:
            result = service.create_payment_intent(order)
            return Response(result, status=status.HTTP_201_CREATED)
        except stripe.error.StripeError as e:
            return Response(
                {"error": f"Payment processing error: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    @action(detail=False, methods=["post"])
    def refund(self, request):
        """
        Create a refund for a payment.

        POST body:
        - order_id: UUID of the order
        - amount: Decimal amount to refund
        - reason: Refund reason code
        - reason_detail: Optional text explanation
        """
        serializer = RefundCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order_id = serializer.validated_data["order_id"]

        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Permission check: customer (own order), store owner, or admin
        user = request.user
        if not (
            order.customer == user
            or (user.is_store_owner and order.store.owner == user)
            or user.is_admin_user
            or user.is_superuser
        ):
            return Response(
                {"error": "You do not have permission to refund this order."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not hasattr(order, "payment"):
            return Response(
                {"error": "No payment found for this order."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = order.payment
        if not payment.is_refundable:
            return Response(
                {"error": "This payment is not eligible for refund."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = PaymentService()

        try:
            refund_obj = service.create_refund(
                payment=payment,
                amount=serializer.validated_data["amount"],
                reason=serializer.validated_data["reason"],
                initiated_by=request.user,
                reason_detail=serializer.validated_data.get("reason_detail", ""),
            )
            return Response(
                RefundSerializer(refund_obj).data,
                status=status.HTTP_201_CREATED,
            )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except stripe.error.StripeError as e:
            return Response(
                {"error": f"Refund processing error: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class PromoCodeViewSet(viewsets.ModelViewSet):
    """
    CRUD for promo codes (admin only for write operations).
    Customers can apply promo codes via the apply action.
    """

    serializer_class = PromoCodeSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and (user.is_admin_user or user.is_superuser):
            return PromoCode.objects.all()
        return PromoCode.objects.filter(is_active=True)

    def get_permissions(self):
        if self.action in ("list", "retrieve", "apply"):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsAdmin()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=["post"])
    def apply(self, request):
        """
        Validate and calculate discount for a promo code.

        POST body:
        - code: Promo code string
        - subtotal: Order subtotal amount
        - store_id: Optional store UUID for store-specific promos
        """
        serializer = PromoCodeApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data["code"]
        subtotal = serializer.validated_data["subtotal"]
        store_id = serializer.validated_data.get("store_id")

        try:
            promo = PromoCode.objects.get(code__iexact=code)
        except PromoCode.DoesNotExist:
            return Response(
                {"error": "Invalid promo code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not promo.is_valid:
            return Response(
                {"error": "This promo code has expired or reached its usage limit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check store restriction
        if store_id and promo.applicable_stores.exists():
            if not promo.applicable_stores.filter(id=store_id).exists():
                return Response(
                    {"error": "This promo code is not valid for this store."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Check first order restriction
        if promo.first_order_only:
            if hasattr(request.user, "customer_profile"):
                if request.user.customer_profile.total_orders > 0:
                    return Response(
                        {"error": "This promo code is only for first-time orders."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # Check per-user usage limit
        from apps.orders.models import Order
        user_usage = Order.objects.filter(
            customer=request.user,
            promo_code__iexact=code,
            status__in=[
                Order.Status.CONFIRMED,
                Order.Status.PREPARING,
                Order.Status.READY,
                Order.Status.PICKED_UP,
                Order.Status.EN_ROUTE,
                Order.Status.DELIVERED,
            ],
        ).count()

        if user_usage >= promo.usage_limit_per_user:
            return Response(
                {"error": "You have already used this promo code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check minimum order amount
        if subtotal < promo.minimum_order_amount:
            return Response(
                {
                    "error": (
                        f"Minimum order amount of ${promo.minimum_order_amount} "
                        f"is required for this promo code."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        discount = promo.calculate_discount(subtotal)

        return Response({
            "code": promo.code,
            "discount_type": promo.discount_type,
            "discount_value": str(promo.discount_value),
            "discount_amount": str(discount),
            "description": promo.description,
            "free_delivery": promo.discount_type == PromoCode.DiscountType.FREE_DELIVERY,
        })


@csrf_exempt
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def stripe_webhook(request):
    """
    Handle Stripe webhook events.

    Processes payment confirmations, failures, and refund updates
    sent by Stripe to keep payment records in sync.
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    if not webhook_secret:
        logger.error("Stripe webhook secret is not configured.")
        return HttpResponse(status=500)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret,
        )
    except ValueError:
        logger.error("Invalid Stripe webhook payload.")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        logger.error("Invalid Stripe webhook signature.")
        return HttpResponse(status=400)

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"Stripe webhook received: {event_type}")

    service = PaymentService()

    if event_type == "payment_intent.succeeded":
        payment_intent_id = data["id"]
        service.confirm_payment(payment_intent_id)

    elif event_type == "payment_intent.payment_failed":
        payment_intent_id = data["id"]
        failure_message = data.get("last_payment_error", {}).get("message", "Unknown error")
        try:
            payment = Payment.objects.get(
                stripe_payment_intent_id=payment_intent_id,
            )
            payment.mark_failed(failure_message)

            # Update order payment status
            payment.order.payment_status = Order.PaymentStatus.FAILED
            payment.order.save(update_fields=["payment_status"])

            logger.info(
                f"Payment failed for order {payment.order.order_number}: {failure_message}"
            )
        except Payment.DoesNotExist:
            logger.warning(
                f"Payment not found for failed intent: {payment_intent_id}"
            )

    elif event_type == "charge.refunded":
        payment_intent_id = data.get("payment_intent")
        if payment_intent_id:
            try:
                payment = Payment.objects.get(
                    stripe_payment_intent_id=payment_intent_id,
                )
                # Update will happen through our refund flow
                logger.info(
                    f"Charge refund event received for order {payment.order.order_number}"
                )
            except Payment.DoesNotExist:
                logger.warning(
                    f"Payment not found for refund event: {payment_intent_id}"
                )

    return HttpResponse(status=200)
