"""
Payment service layer for FreshCart.

Provides a clean interface for interacting with the Stripe API.
All payment logic is centralized here to keep views thin.
"""

import logging
from decimal import Decimal

import stripe
from django.conf import settings

from .models import Payment, Refund

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Service class that wraps Stripe API operations for order payments.

    Usage:
        service = PaymentService()
        intent = service.create_payment_intent(order)
        service.capture_payment(payment_intent_id)
    """

    def __init__(self):
        stripe.api_key = settings.STRIPE_SECRET_KEY

    def create_payment_intent(self, order):
        """
        Create a Stripe PaymentIntent for the given order.

        Returns:
            dict: Contains client_secret for frontend confirmation and
                  the Payment model instance.
        """
        amount_cents = int(order.total_amount * 100)

        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                metadata={
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "customer_email": order.customer.email,
                    "store_name": order.store.name,
                },
                automatic_payment_methods={"enabled": True},
                capture_method="manual",  # Authorize now, capture on delivery
            )

            # Create Payment record
            payment = Payment.objects.create(
                order=order,
                customer=order.customer,
                method=Payment.Method.STRIPE,
                status=Payment.Status.PROCESSING,
                amount=order.total_amount,
                stripe_payment_intent_id=intent.id,
                stripe_client_secret=intent.client_secret,
            )

            logger.info(
                f"PaymentIntent created for order {order.order_number}: {intent.id}"
            )

            return {
                "client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
                "payment_id": str(payment.id),
            }

        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe error creating PaymentIntent for order "
                f"{order.order_number}: {e}"
            )
            raise

    def confirm_payment(self, payment_intent_id):
        """
        Process a confirmed payment after frontend confirmation.

        Called by the Stripe webhook when payment_intent.succeeded fires.
        Updates the Payment record to authorized status.
        """
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)

            payment = Payment.objects.get(
                stripe_payment_intent_id=payment_intent_id,
            )

            if intent.status == "requires_capture":
                charge = intent.latest_charge
                charge_obj = stripe.Charge.retrieve(charge) if charge else None

                payment.mark_authorized(
                    payment_intent_id=payment_intent_id,
                    charge_id=charge or "",
                )

                # Store card details for display
                if charge_obj and charge_obj.payment_method_details:
                    card = charge_obj.payment_method_details.get("card", {})
                    payment.card_last_four = card.get("last4", "")
                    payment.card_brand = card.get("brand", "")
                    payment.save(update_fields=["card_last_four", "card_brand"])

                # Update order payment status
                from apps.orders.models import Order
                payment.order.payment_status = Order.PaymentStatus.AUTHORIZED
                payment.order.payment_intent_id = payment_intent_id
                payment.order.save(update_fields=[
                    "payment_status", "payment_intent_id",
                ])

                logger.info(
                    f"Payment authorized for order {payment.order.order_number}"
                )
                return True

            elif intent.status == "succeeded":
                payment.mark_captured()
                return True

            else:
                payment.mark_failed(f"Unexpected intent status: {intent.status}")
                return False

        except Payment.DoesNotExist:
            logger.error(f"Payment not found for intent: {payment_intent_id}")
            return False
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error confirming payment: {e}")
            return False

    def capture_payment(self, payment_intent_id):
        """
        Capture an authorized payment (charge the customer).

        Called when an order is delivered to actually collect the funds.
        """
        try:
            intent = stripe.PaymentIntent.capture(payment_intent_id)

            payment = Payment.objects.get(
                stripe_payment_intent_id=payment_intent_id,
            )

            if intent.status == "succeeded":
                payment.mark_captured()
                logger.info(
                    f"Payment captured for order {payment.order.order_number}"
                )
                return True
            else:
                payment.mark_failed(f"Capture returned status: {intent.status}")
                return False

        except Payment.DoesNotExist:
            logger.error(f"Payment not found for intent: {payment_intent_id}")
            return False
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error capturing payment: {e}")
            return False

    def create_refund(self, payment, amount, reason, initiated_by=None, reason_detail=""):
        """
        Create a refund for a payment.

        Args:
            payment: Payment model instance
            amount: Decimal amount to refund
            reason: Refund.Reason choice
            initiated_by: User who initiated the refund
            reason_detail: Additional detail about the refund reason

        Returns:
            Refund instance if successful, raises exception otherwise.
        """
        refund_record = Refund(
            payment=payment,
            amount=amount,
            reason=reason,
            reason_detail=reason_detail,
            initiated_by=initiated_by,
        )

        # Validate the refund amount
        refund_record.validate_amount()

        if payment.method == Payment.Method.CASH:
            # Cash payments are tracked but not processed through Stripe
            refund_record.status = Refund.Status.COMPLETED
            refund_record.save()
            self._update_payment_after_refund(payment)
            logger.info(
                f"Cash refund of ${amount} recorded for payment {payment.id}"
            )
            return refund_record

        try:
            amount_cents = int(amount * 100)
            stripe_refund = stripe.Refund.create(
                payment_intent=payment.stripe_payment_intent_id,
                amount=amount_cents,
                reason="requested_by_customer",
                metadata={
                    "order_number": payment.order.order_number,
                    "refund_reason": reason,
                },
            )

            refund_record.stripe_refund_id = stripe_refund.id
            refund_record.status = Refund.Status.COMPLETED
            refund_record.save()

            self._update_payment_after_refund(payment)

            logger.info(
                f"Stripe refund of ${amount} processed for payment {payment.id}"
            )
            return refund_record

        except stripe.error.StripeError as e:
            refund_record.status = Refund.Status.FAILED
            refund_record.failure_reason = str(e)
            refund_record.save()
            logger.error(f"Stripe refund failed for payment {payment.id}: {e}")
            raise

    def _update_payment_after_refund(self, payment):
        """Update payment status after a refund is processed."""
        from django.utils import timezone

        if payment.refunded_amount >= payment.amount:
            payment.status = Payment.Status.REFUNDED
        else:
            payment.status = Payment.Status.PARTIALLY_REFUNDED
        payment.save(update_fields=["status", "updated_at"])

    def create_cash_payment(self, order):
        """
        Create a payment record for cash-on-delivery orders.
        No Stripe interaction needed.
        """
        payment = Payment.objects.create(
            order=order,
            customer=order.customer,
            method=Payment.Method.CASH,
            status=Payment.Status.PENDING,
            amount=order.total_amount,
        )
        logger.info(
            f"Cash payment created for order {order.order_number}"
        )
        return payment

    def mark_cash_collected(self, order):
        """Mark a cash payment as collected upon delivery."""
        try:
            payment = Payment.objects.get(
                order=order,
                method=Payment.Method.CASH,
            )
            payment.mark_captured()
            logger.info(
                f"Cash collected for order {order.order_number}"
            )
            return True
        except Payment.DoesNotExist:
            logger.error(
                f"Cash payment not found for order {order.order_number}"
            )
            return False
