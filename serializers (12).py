"""
Delivery views for FreshCart.

Handles delivery zone management, driver location updates,
and delivery assignment operations.
"""

import logging

from django.contrib.gis.geos import Point
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import DriverProfile
from apps.accounts.permissions import IsAdmin, IsDriver, IsVerifiedDriver
from apps.orders.models import DeliveryTracking, Order

from .models import DeliveryAssignment, DeliveryZone, DriverLocation
from .serializers import (
    ActiveDeliverySerializer,
    DeliveryAssignmentSerializer,
    DeliveryZoneCheckSerializer,
    DeliveryZoneSerializer,
    DriverLocationSerializer,
    DriverLocationUpdateSerializer,
)

logger = logging.getLogger(__name__)


class DeliveryZoneViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for delivery zones.
    Read access for all, write access for admins only.
    """

    queryset = DeliveryZone.objects.filter(is_active=True)
    serializer_class = DeliveryZoneSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "check_zone"):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsAdmin()]

    @action(detail=False, methods=["post"], url_path="check")
    def check_zone(self, request):
        """
        Check if coordinates are within any delivery zone.

        POST body:
        - latitude: float
        - longitude: float
        """
        serializer = DeliveryZoneCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        point = Point(
            serializer.validated_data["longitude"],
            serializer.validated_data["latitude"],
            srid=4326,
        )

        matching_zones = DeliveryZone.objects.filter(
            is_active=True,
            boundary__contains=point,
        )

        if matching_zones.exists():
            zone_data = DeliveryZoneSerializer(matching_zones, many=True).data
            return Response(
                {
                    "is_serviceable": True,
                    "zones": zone_data,
                }
            )

        return Response(
            {
                "is_serviceable": False,
                "zones": [],
                "message": "This location is not within any delivery zone.",
            }
        )


class DriverLocationUpdateView(generics.CreateAPIView):
    """
    Update driver's current location.
    Stores location in the database and broadcasts via WebSocket.
    """

    serializer_class = DriverLocationUpdateSerializer
    permission_classes = [permissions.IsAuthenticated, IsDriver]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        driver = request.user
        location = Point(data["longitude"], data["latitude"], srid=4326)

        # Update driver profile location
        if hasattr(driver, "driver_profile"):
            driver.driver_profile.current_location = location
            driver.driver_profile.save(update_fields=["current_location", "updated_at"])

        # Check if driver is on active delivery
        active_order = Order.objects.filter(
            driver=driver,
            status__in=[Order.Status.PICKED_UP, Order.Status.EN_ROUTE],
        ).first()

        # Save location snapshot to database
        driver_location = DriverLocation.objects.create(
            driver=driver,
            location=location,
            heading=data.get("heading"),
            speed_kmh=data.get("speed_kmh"),
            accuracy_meters=data.get("accuracy_meters"),
            altitude=data.get("altitude"),
            battery_level=data.get("battery_level"),
            order=active_order,
            is_active_delivery=active_order is not None,
        )

        # Broadcast location via WebSocket
        if active_order:
            self._broadcast_location(active_order, data)

        return Response(
            {
                "message": "Location updated.",
                "location_id": str(driver_location.id),
            },
            status=status.HTTP_200_OK,
        )

    def _broadcast_location(self, order, location_data):
        """Broadcast driver location to order tracking WebSocket."""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"order_{order.id}",
                {
                    "type": "order.driver_location",
                    "data": {
                        "order_id": str(order.id),
                        "latitude": location_data["latitude"],
                        "longitude": location_data["longitude"],
                        "heading": location_data.get("heading"),
                        "speed_kmh": location_data.get("speed_kmh"),
                        "timestamp": timezone.now().isoformat(),
                    },
                },
            )
        except Exception as e:
            logger.error(f"Failed to broadcast driver location: {e}")


class ActiveDeliveryView(generics.RetrieveAPIView):
    """Get the driver's current active delivery."""

    permission_classes = [permissions.IsAuthenticated, IsDriver]

    def retrieve(self, request, *args, **kwargs):
        driver = request.user

        active_order = (
            Order.objects.filter(
                driver=driver,
                status__in=[
                    Order.Status.READY,
                    Order.Status.PICKED_UP,
                    Order.Status.EN_ROUTE,
                ],
            )
            .select_related("store", "customer")
            .first()
        )

        if not active_order:
            return Response(
                {"message": "No active delivery."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = {
            "order_id": active_order.id,
            "order_number": active_order.order_number,
            "status": active_order.status,
            "store_name": active_order.store.name,
            "store_address": active_order.store.address_line_1,
            "store_latitude": (
                active_order.store.location.y if active_order.store.location else 0
            ),
            "store_longitude": (
                active_order.store.location.x if active_order.store.location else 0
            ),
            "customer_name": active_order.customer.get_full_name(),
            "delivery_address": active_order.delivery_address,
            "delivery_latitude": (
                active_order.delivery_location.y if active_order.delivery_location else 0
            ),
            "delivery_longitude": (
                active_order.delivery_location.x if active_order.delivery_location else 0
            ),
            "delivery_instructions": active_order.delivery_instructions,
            "delivery_fee": active_order.delivery_fee,
            "tip_amount": active_order.tip_amount,
            "items_count": active_order.item_count,
            "created_at": active_order.created_at,
        }

        serializer = ActiveDeliverySerializer(data)
        return Response(serializer.data)


class DeliveryAssignmentView(generics.GenericAPIView):
    """Handle delivery assignment acceptance or decline."""

    permission_classes = [permissions.IsAuthenticated, IsVerifiedDriver]

    def post(self, request, order_id):
        """Accept a delivery assignment."""
        driver = request.user

        try:
            order = Order.objects.get(
                id=order_id,
                status=Order.Status.READY,
            )
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found or no longer available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if order already has a driver
        if order.driver:
            return Response(
                {"error": "This order has already been assigned to a driver."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if driver is available
        if not hasattr(driver, "driver_profile") or not driver.driver_profile.is_available:
            return Response(
                {"error": "You are not available for deliveries."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Assign driver
        order.driver = driver
        order.save(update_fields=["driver"])

        # Update driver status
        driver.driver_profile.availability_status = DriverProfile.AvailabilityStatus.ON_DELIVERY
        driver.driver_profile.save(update_fields=["availability_status"])

        # Create or update delivery assignment record
        DeliveryAssignment.objects.update_or_create(
            order=order,
            driver=driver,
            defaults={
                "response_status": DeliveryAssignment.ResponseStatus.ACCEPTED,
                "responded_at": timezone.now(),
            },
        )

        # Create tracking event
        DeliveryTracking.objects.create(
            order=order,
            event_type=DeliveryTracking.EventType.DRIVER_ASSIGNED,
            status=order.status,
            description=f"Driver {driver.get_full_name()} accepted the delivery.",
            created_by=driver,
        )

        # Notify customer via WebSocket
        from apps.orders.tasks import notify_order_status_change

        notify_order_status_change.delay(str(order.id), order.status)

        logger.info(
            f"Driver {driver.email} accepted delivery for order {order.order_number}"
        )

        return Response(
            {"message": "Delivery accepted.", "order_number": order.order_number},
            status=status.HTTP_200_OK,
        )

    def delete(self, request, order_id):
        """Decline a delivery assignment."""
        driver = request.user

        try:
            assignment = DeliveryAssignment.objects.get(
                order_id=order_id,
                driver=driver,
                response_status=DeliveryAssignment.ResponseStatus.PENDING,
            )
        except DeliveryAssignment.DoesNotExist:
            return Response(
                {"error": "Assignment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        assignment.response_status = DeliveryAssignment.ResponseStatus.DECLINED
        assignment.responded_at = timezone.now()
        assignment.save(update_fields=["response_status", "responded_at"])

        logger.info(
            f"Driver {driver.email} declined delivery for order {assignment.order.order_number}"
        )

        # Re-trigger assignment to find next driver
        from apps.orders.tasks import process_order_auto_assignment

        process_order_auto_assignment.delay(str(order_id))

        return Response(
            {"message": "Delivery declined."},
            status=status.HTTP_200_OK,
        )


class DriverDeliveryHistoryView(generics.ListAPIView):
    """List completed deliveries for the authenticated driver."""

    permission_classes = [permissions.IsAuthenticated, IsDriver]

    def get(self, request, *args, **kwargs):
        deliveries = (
            Order.objects.filter(
                driver=request.user,
                status=Order.Status.DELIVERED,
            )
            .select_related("store", "customer")
            .order_by("-delivered_at")
        )

        page = self.paginate_queryset(deliveries)
        from apps.orders.serializers import OrderListSerializer

        if page is not None:
            serializer = OrderListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = OrderListSerializer(deliveries, many=True)
        return Response(serializer.data)


class DriverEarningsView(generics.RetrieveAPIView):
    """Get earnings summary for the authenticated driver."""

    permission_classes = [permissions.IsAuthenticated, IsDriver]

    def retrieve(self, request, *args, **kwargs):
        from django.db.models import Sum
        from datetime import timedelta

        driver = request.user
        profile = driver.driver_profile

        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        deliveries = Order.objects.filter(
            driver=driver,
            status=Order.Status.DELIVERED,
        )

        earnings_today = (
            deliveries.filter(delivered_at__date=today).aggregate(
                delivery_fees=Sum("delivery_fee"),
                tips=Sum("tip_amount"),
            )
        )

        earnings_week = (
            deliveries.filter(delivered_at__date__gte=week_start).aggregate(
                delivery_fees=Sum("delivery_fee"),
                tips=Sum("tip_amount"),
            )
        )

        earnings_month = (
            deliveries.filter(delivered_at__date__gte=month_start).aggregate(
                delivery_fees=Sum("delivery_fee"),
                tips=Sum("tip_amount"),
            )
        )

        return Response(
            {
                "total_earnings": float(profile.total_earnings),
                "total_deliveries": profile.total_deliveries,
                "rating": float(profile.rating),
                "average_delivery_time_minutes": profile.average_delivery_time_minutes,
                "today": {
                    "delivery_fees": float(earnings_today["delivery_fees"] or 0),
                    "tips": float(earnings_today["tips"] or 0),
                    "total": float(
                        (earnings_today["delivery_fees"] or 0)
                        + (earnings_today["tips"] or 0)
                    ),
                    "deliveries": deliveries.filter(delivered_at__date=today).count(),
                },
                "this_week": {
                    "delivery_fees": float(earnings_week["delivery_fees"] or 0),
                    "tips": float(earnings_week["tips"] or 0),
                    "total": float(
                        (earnings_week["delivery_fees"] or 0)
                        + (earnings_week["tips"] or 0)
                    ),
                    "deliveries": deliveries.filter(
                        delivered_at__date__gte=week_start
                    ).count(),
                },
                "this_month": {
                    "delivery_fees": float(earnings_month["delivery_fees"] or 0),
                    "tips": float(earnings_month["tips"] or 0),
                    "total": float(
                        (earnings_month["delivery_fees"] or 0)
                        + (earnings_month["tips"] or 0)
                    ),
                    "deliveries": deliveries.filter(
                        delivered_at__date__gte=month_start
                    ).count(),
                },
            }
        )
