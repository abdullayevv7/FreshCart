"""
Celery tasks for FreshCart orders.

Handles background processing for:
- Order status notifications via WebSocket
- Automatic driver assignment
- Stale order cleanup
- Low stock alerts
- Daily sales summaries
"""

import logging
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db.models import F, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    queue="notifications",
    max_retries=3,
    default_retry_delay=5,
)
def notify_order_status_change(self, order_id, new_status):
    """
    Send real-time WebSocket notification when order status changes.
    Notifies the customer and store owner.
    """
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        from apps.orders.models import Order

        order = Order.objects.select_related("customer", "store", "driver").get(
            id=order_id
        )
        channel_layer = get_channel_layer()

        # Send to order tracking WebSocket group
        message = {
            "type": "order.status_update",
            "data": {
                "order_id": str(order.id),
                "order_number": order.order_number,
                "status": new_status,
                "store_name": order.store.name,
                "updated_at": timezone.now().isoformat(),
            },
        }

        async_to_sync(channel_layer.group_send)(
            f"order_{order_id}",
            message,
        )

        logger.info(
            f"WebSocket notification sent for order {order.order_number}: {new_status}"
        )

    except Exception as exc:
        logger.error(f"Failed to send order notification: {exc}")
        self.retry(exc=exc)


@shared_task(
    bind=True,
    queue="orders",
    max_retries=3,
    default_retry_delay=10,
)
def process_order_auto_assignment(self, order_id):
    """
    Automatically assign a delivery driver to a ready order.
    Finds the nearest available driver within the store's delivery zone.
    """
    try:
        from django.contrib.gis.db.models.functions import Distance
        from django.contrib.gis.measure import D

        from apps.accounts.models import DriverProfile
        from apps.orders.models import DeliveryTracking, Order

        order = Order.objects.select_related("store").get(id=order_id)

        if order.status != Order.Status.READY:
            logger.warning(
                f"Order {order.order_number} is not in READY status, skipping assignment."
            )
            return

        if order.driver:
            logger.info(
                f"Order {order.order_number} already has a driver assigned."
            )
            return

        store_location = order.store.location

        # Find available drivers near the store
        available_drivers = (
            DriverProfile.objects.filter(
                availability_status=DriverProfile.AvailabilityStatus.ONLINE,
                is_verified=True,
                current_location__isnull=False,
                current_location__distance_lte=(
                    store_location,
                    D(km=order.store.delivery_radius_km),
                ),
            )
            .annotate(distance=Distance("current_location", store_location))
            .order_by("distance")
        )

        if not available_drivers.exists():
            logger.warning(
                f"No available drivers found for order {order.order_number}."
            )
            # Retry after timeout period
            timeout = settings.FRESHCART.get("DRIVER_ASSIGNMENT_TIMEOUT_SECONDS", 60)
            self.retry(countdown=timeout)
            return

        # Assign the nearest driver
        driver_profile = available_drivers.first()
        driver_user = driver_profile.user

        order.driver = driver_user
        order.save(update_fields=["driver"])

        # Update driver status
        driver_profile.availability_status = DriverProfile.AvailabilityStatus.ON_DELIVERY
        driver_profile.save(update_fields=["availability_status"])

        # Create tracking event
        DeliveryTracking.objects.create(
            order=order,
            event_type=DeliveryTracking.EventType.DRIVER_ASSIGNED,
            status=order.status,
            description=f"Driver {driver_user.get_full_name()} assigned to delivery.",
            created_by=driver_user,
        )

        # Notify driver via WebSocket
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"driver_{driver_user.id}",
            {
                "type": "delivery.assignment",
                "data": {
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "store_name": order.store.name,
                    "store_address": order.store.address_line_1,
                    "delivery_address": order.delivery_address,
                    "total_amount": str(order.total_amount),
                    "delivery_fee": str(order.delivery_fee),
                    "tip_amount": str(order.tip_amount),
                },
            },
        )

        logger.info(
            f"Driver {driver_user.email} assigned to order {order.order_number}"
        )

    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found for auto-assignment.")
    except Exception as exc:
        logger.error(f"Driver assignment failed for order {order_id}: {exc}")
        self.retry(exc=exc)


@shared_task(queue="orders")
def cancel_stale_orders():
    """
    Cancel orders that have been pending for too long.
    Runs every 5 minutes via Celery Beat.
    """
    from apps.orders.models import Order

    timeout_minutes = settings.FRESHCART.get("ORDER_AUTO_CANCEL_MINUTES", 30)
    cutoff_time = timezone.now() - timedelta(minutes=timeout_minutes)

    stale_orders = Order.objects.filter(
        status=Order.Status.PENDING,
        created_at__lt=cutoff_time,
    )

    count = 0
    for order in stale_orders:
        try:
            order.transition_to(
                Order.Status.CANCELLED,
                reason=f"Auto-cancelled: no response within {timeout_minutes} minutes.",
                cancelled_by="system",
            )

            # Restore stock
            for item in order.items.all():
                if item.product:
                    item.product.restore_stock(item.quantity)

            # Notify via WebSocket
            notify_order_status_change.delay(str(order.id), Order.Status.CANCELLED)
            count += 1
        except ValueError:
            pass

    if count > 0:
        logger.info(f"Auto-cancelled {count} stale orders.")


@shared_task(queue="notifications")
def check_low_stock_alerts():
    """
    Check for products with low stock and log alerts.
    Runs every 2 hours via Celery Beat.
    """
    from apps.products.models import GroceryProduct

    low_stock_products = GroceryProduct.objects.filter(
        is_available=True,
        stock_quantity__lte=F("low_stock_threshold"),
        stock_quantity__gt=0,
    ).select_related("store", "store__owner")

    if not low_stock_products.exists():
        return

    # Group by store owner for notifications
    store_alerts = {}
    for product in low_stock_products:
        owner_email = product.store.owner.email
        if owner_email not in store_alerts:
            store_alerts[owner_email] = []
        store_alerts[owner_email].append(
            {
                "product_name": product.name,
                "store_name": product.store.name,
                "current_stock": product.stock_quantity,
                "threshold": product.low_stock_threshold,
            }
        )

    for email, products in store_alerts.items():
        logger.info(
            f"Low stock alert for {email}: {len(products)} products below threshold."
        )
        # In production, send email notification here
        # send_low_stock_email.delay(email, products)

    logger.info(f"Low stock check complete: {low_stock_products.count()} products flagged.")


@shared_task(queue="default")
def cleanup_stale_driver_locations():
    """
    Reset drivers with stale location data to offline status.
    Runs every 10 minutes via Celery Beat.
    """
    from apps.accounts.models import DriverProfile

    # Drivers who haven't updated location in 15 minutes are considered stale
    stale_cutoff = timezone.now() - timedelta(minutes=15)

    stale_drivers = DriverProfile.objects.filter(
        availability_status=DriverProfile.AvailabilityStatus.ONLINE,
        updated_at__lt=stale_cutoff,
    )

    count = stale_drivers.update(
        availability_status=DriverProfile.AvailabilityStatus.OFFLINE
    )

    if count > 0:
        logger.info(f"Set {count} stale drivers to offline.")


@shared_task(queue="default")
def generate_daily_sales_summary():
    """
    Generate a daily sales summary for all active stores.
    Runs at 2:00 AM UTC via Celery Beat.
    """
    from apps.orders.models import Order
    from apps.stores.models import Store

    yesterday = timezone.now().date() - timedelta(days=1)

    active_stores = Store.objects.filter(status=Store.Status.ACTIVE)

    for store in active_stores:
        orders = Order.objects.filter(
            store=store,
            status=Order.Status.DELIVERED,
            delivered_at__date=yesterday,
        )

        if not orders.exists():
            continue

        summary = orders.aggregate(
            total_revenue=Sum("total_amount"),
            total_orders=Sum("id"),
            total_delivery_fees=Sum("delivery_fee"),
            total_tips=Sum("tip_amount"),
        )

        logger.info(
            f"Daily summary for {store.name} ({yesterday}): "
            f"Revenue: ${summary['total_revenue'] or 0}, "
            f"Orders: {orders.count()}"
        )


@shared_task(
    bind=True,
    queue="orders",
    max_retries=2,
    default_retry_delay=30,
)
def process_order_payment(self, order_id):
    """
    Process payment capture for a delivered order.
    """
    try:
        from apps.orders.models import Order
        from apps.payments.services import PaymentService

        order = Order.objects.get(id=order_id)

        if order.payment_status != Order.PaymentStatus.AUTHORIZED:
            logger.warning(
                f"Order {order.order_number} payment not in authorized state."
            )
            return

        payment_service = PaymentService()
        success = payment_service.capture_payment(order.payment_intent_id)

        if success:
            order.payment_status = Order.PaymentStatus.CAPTURED
            order.save(update_fields=["payment_status"])
            logger.info(
                f"Payment captured for order {order.order_number}"
            )
        else:
            logger.error(
                f"Payment capture failed for order {order.order_number}"
            )

    except Exception as exc:
        logger.error(f"Payment processing failed: {exc}")
        self.retry(exc=exc)
