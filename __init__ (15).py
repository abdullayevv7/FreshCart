"""
WebSocket consumers for real-time order tracking.

Handles:
- Order status updates for customers and store owners
- Live delivery tracking with driver location
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebSocketConsumer

logger = logging.getLogger(__name__)


class OrderTrackingConsumer(AsyncJsonWebSocketConsumer):
    """
    WebSocket consumer for real-time order status updates.

    Clients connect to: ws/orders/{order_id}/
    Receives order status changes and broadcasts to connected clients.
    """

    async def connect(self):
        self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
        self.group_name = f"order_{self.order_id}"
        user = self.scope.get("user")

        # Verify the user has permission to track this order
        if user and user.is_authenticated:
            has_access = await self.verify_order_access(user, self.order_id)
            if not has_access:
                await self.close(code=4003)
                return

            # Join the order tracking group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name,
            )
            await self.accept()

            # Send current order status
            order_data = await self.get_order_status(self.order_id)
            if order_data:
                await self.send_json({
                    "type": "order.current_status",
                    "data": order_data,
                })

            logger.info(
                f"WebSocket connected: order tracking for {self.order_id} "
                f"by user {user.email}"
            )
        else:
            await self.close(code=4001)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )
            logger.info(
                f"WebSocket disconnected: order tracking for {self.order_id}"
            )

    async def receive_json(self, content, **kwargs):
        """Handle incoming messages from the client."""
        message_type = content.get("type")

        if message_type == "ping":
            await self.send_json({"type": "pong"})

    async def order_status_update(self, event):
        """Handle order status update events from the channel layer."""
        await self.send_json({
            "type": "order.status_update",
            "data": event["data"],
        })

    async def order_driver_location(self, event):
        """Handle driver location updates for the order."""
        await self.send_json({
            "type": "order.driver_location",
            "data": event["data"],
        })

    async def delivery_assignment(self, event):
        """Handle driver assignment notification."""
        await self.send_json({
            "type": "order.driver_assigned",
            "data": event["data"],
        })

    @database_sync_to_async
    def verify_order_access(self, user, order_id):
        """Verify the user has permission to track this order."""
        from apps.orders.models import Order

        try:
            order = Order.objects.get(id=order_id)
            # Customer, store owner, assigned driver, or admin can track
            return (
                order.customer == user
                or order.store.owner == user
                or order.driver == user
                or user.is_superuser
                or user.is_admin_user
            )
        except Order.DoesNotExist:
            return False

    @database_sync_to_async
    def get_order_status(self, order_id):
        """Get the current order status data."""
        from apps.orders.models import Order

        try:
            order = Order.objects.select_related(
                "store", "customer", "driver"
            ).get(id=order_id)

            data = {
                "order_id": str(order.id),
                "order_number": order.order_number,
                "status": order.status,
                "store_name": order.store.name,
                "estimated_delivery_time": (
                    order.estimated_delivery_time.isoformat()
                    if order.estimated_delivery_time
                    else None
                ),
                "driver_name": (
                    order.driver.get_full_name() if order.driver else None
                ),
                "created_at": order.created_at.isoformat(),
            }

            # Include tracking events
            events = order.tracking_events.all()[:10]
            data["tracking_events"] = [
                {
                    "event_type": e.event_type,
                    "status": e.status,
                    "description": e.description,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ]

            return data
        except Order.DoesNotExist:
            return None
