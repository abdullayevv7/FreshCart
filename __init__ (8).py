"""
WebSocket consumer for live driver location tracking.

Provides real-time location updates to customers tracking
their delivery and to drivers receiving assignment offers.
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebSocketConsumer

logger = logging.getLogger(__name__)


class DriverLocationConsumer(AsyncJsonWebSocketConsumer):
    """
    WebSocket consumer for real-time driver location broadcasting.

    Two modes of operation:
    1. Delivery tracking (ws/delivery/{order_id}/):
       Customers subscribe to receive driver location updates for their order.

    2. Driver channel (ws/driver/):
       Drivers subscribe to receive new delivery assignment offers and
       push their own location updates.
    """

    async def connect(self):
        user = self.scope.get("user")

        if not (user and user.is_authenticated):
            await self.close(code=4001)
            return

        # Determine mode based on URL route
        self.order_id = self.scope["url_route"]["kwargs"].get("order_id")

        if self.order_id:
            # Mode 1: Delivery tracking (customer watching driver)
            self.group_name = f"delivery_{self.order_id}"
            has_access = await self.verify_delivery_access(user, self.order_id)
            if not has_access:
                await self.close(code=4003)
                return
        else:
            # Mode 2: Driver channel (receiving assignments and pushing location)
            is_driver = await self.check_is_driver(user)
            if not is_driver:
                await self.close(code=4003)
                return
            self.group_name = f"driver_{user.id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )
        await self.accept()

        logger.info(
            f"WebSocket connected: {self.group_name} by user {user.email}"
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )
            logger.info(f"WebSocket disconnected: {self.group_name}")

    async def receive_json(self, content, **kwargs):
        """
        Handle incoming messages from the client.

        Drivers can send location updates via this WebSocket:
        {
            "type": "location_update",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "heading": 90.0,
            "speed_kmh": 30.0
        }
        """
        message_type = content.get("type")
        user = self.scope.get("user")

        if message_type == "ping":
            await self.send_json({"type": "pong"})
            return

        if message_type == "location_update" and user:
            is_driver = await self.check_is_driver(user)
            if not is_driver:
                await self.send_json({
                    "type": "error",
                    "message": "Only drivers can send location updates.",
                })
                return

            # Save location and broadcast to active orders
            await self.handle_driver_location_update(user, content)

    async def handle_driver_location_update(self, user, content):
        """Process and broadcast a driver location update."""
        latitude = content.get("latitude")
        longitude = content.get("longitude")
        heading = content.get("heading")
        speed_kmh = content.get("speed_kmh")

        if latitude is None or longitude is None:
            await self.send_json({
                "type": "error",
                "message": "latitude and longitude are required.",
            })
            return

        # Save location to database
        active_order_id = await self.save_driver_location(
            user, latitude, longitude, heading, speed_kmh,
        )

        # Broadcast to order tracking if driver is on active delivery
        if active_order_id:
            await self.channel_layer.group_send(
                f"order_{active_order_id}",
                {
                    "type": "order.driver_location",
                    "data": {
                        "order_id": str(active_order_id),
                        "latitude": latitude,
                        "longitude": longitude,
                        "heading": heading,
                        "speed_kmh": speed_kmh,
                    },
                },
            )

            # Also broadcast to delivery-specific channel
            await self.channel_layer.group_send(
                f"delivery_{active_order_id}",
                {
                    "type": "driver.location",
                    "data": {
                        "latitude": latitude,
                        "longitude": longitude,
                        "heading": heading,
                        "speed_kmh": speed_kmh,
                    },
                },
            )

        await self.send_json({
            "type": "location_ack",
            "message": "Location updated.",
        })

    # ── Channel layer event handlers ───────────────────

    async def driver_location(self, event):
        """Forward driver location to the connected client."""
        await self.send_json({
            "type": "driver.location",
            "data": event["data"],
        })

    async def delivery_assignment(self, event):
        """Forward new delivery assignment to the driver."""
        await self.send_json({
            "type": "delivery.new_assignment",
            "data": event["data"],
        })

    async def delivery_cancelled(self, event):
        """Notify driver that their assignment was cancelled."""
        await self.send_json({
            "type": "delivery.cancelled",
            "data": event["data"],
        })

    async def order_status_update(self, event):
        """Forward order status changes to tracking clients."""
        await self.send_json({
            "type": "order.status_update",
            "data": event["data"],
        })

    # ── Database operations ────────────────────────────

    @database_sync_to_async
    def verify_delivery_access(self, user, order_id):
        """Check that the user can view delivery tracking for this order."""
        from apps.orders.models import Order

        try:
            order = Order.objects.get(id=order_id)
            return (
                order.customer == user
                or order.driver == user
                or order.store.owner == user
                or user.is_superuser
                or user.is_admin_user
            )
        except Order.DoesNotExist:
            return False

    @database_sync_to_async
    def check_is_driver(self, user):
        """Check if the user is a delivery driver."""
        return hasattr(user, "role") and user.role == "driver"

    @database_sync_to_async
    def save_driver_location(self, user, latitude, longitude, heading, speed_kmh):
        """
        Save driver location snapshot and update profile.
        Returns the active order ID if the driver is on a delivery.
        """
        from django.contrib.gis.geos import Point
        from apps.delivery.models import DriverLocation
        from apps.orders.models import Order

        location = Point(longitude, latitude, srid=4326)

        # Update driver profile
        if hasattr(user, "driver_profile"):
            user.driver_profile.current_location = location
            user.driver_profile.save(
                update_fields=["current_location", "updated_at"]
            )

        # Check for active delivery
        active_order = Order.objects.filter(
            driver=user,
            status__in=[Order.Status.PICKED_UP, Order.Status.EN_ROUTE],
        ).first()

        # Save location snapshot
        DriverLocation.objects.create(
            driver=user,
            location=location,
            heading=heading,
            speed_kmh=speed_kmh,
            order=active_order,
            is_active_delivery=active_order is not None,
        )

        return active_order.id if active_order else None
