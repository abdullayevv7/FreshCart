"""
WebSocket URL routing for FreshCart.

Defines the WebSocket endpoints for real-time features:
- Order status updates
- Live delivery tracking
- Driver assignment notifications
"""

from django.urls import re_path

from apps.delivery.consumers import DriverLocationConsumer
from apps.orders.consumers import OrderTrackingConsumer

websocket_urlpatterns = [
    # Real-time order status updates for a specific order
    # Used by customers and store owners to see live order state changes
    re_path(
        r"ws/orders/(?P<order_id>[0-9a-f-]+)/$",
        OrderTrackingConsumer.as_asgi(),
    ),
    # Live driver location updates for delivery tracking
    # Used by customers to see the driver on the map
    re_path(
        r"ws/delivery/(?P<order_id>[0-9a-f-]+)/$",
        DriverLocationConsumer.as_asgi(),
    ),
    # Driver notification channel for new assignment requests
    # Used by drivers to receive real-time delivery assignment offers
    re_path(
        r"ws/driver/$",
        DriverLocationConsumer.as_asgi(),
    ),
]
