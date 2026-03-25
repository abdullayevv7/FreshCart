"""
Order views for FreshCart.

Handles order creation, status management, and tracking.
"""

import logging

from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAdmin, IsCustomer, IsDriver, IsStoreOwner

from .models import DeliveryTracking, Order, OrderItem
from .serializers import (
    OrderCreateSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    OrderRatingSerializer,
    OrderStatusUpdateSerializer,
)
from .tasks import notify_order_status_change, process_order_auto_assignment

logger = logging.getLogger(__name__)


class OrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for order operations.

    - Customers: Create orders, view their own orders, cancel pending orders
    - Store Owners: View orders for their stores, accept/reject, update status
    - Drivers: View assigned deliveries, update delivery status
    - Admins: Full access
    """

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status", "payment_status"]
    ordering_fields = ["created_at", "total_amount"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        if self.action in ("retrieve",):
            return OrderDetailSerializer
        return OrderListSerializer

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsCustomer()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = Order.objects.select_related("store", "customer", "driver")

        if user.is_admin_user or user.is_superuser:
            return qs

        if user.is_customer:
            return qs.filter(customer=user)

        if user.is_store_owner:
            return qs.filter(store__owner=user)

        if user.is_driver:
            return qs.filter(driver=user)

        return qs.none()

    def perform_create(self, serializer):
        order = serializer.save()
        # Trigger async tasks
        notify_order_status_change.delay(str(order.id), Order.Status.PENDING)
        logger.info(
            f"Order created: {order.order_number} by {self.request.user.email}"
        )

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        """Store owner accepts an order."""
        order = self.get_object()

        if not (request.user.is_store_owner and order.store.owner == request.user):
            return Response(
                {"error": "Only the store owner can accept orders."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            order.transition_to(Order.Status.CONFIRMED)
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Decrement stock for all items
        for item in order.items.all():
            if item.product:
                item.product.decrement_stock(item.quantity)

        DeliveryTracking.objects.create(
            order=order,
            event_type=DeliveryTracking.EventType.STATUS_CHANGE,
            status=Order.Status.CONFIRMED,
            description="Order confirmed by store.",
            created_by=request.user,
        )

        notify_order_status_change.delay(str(order.id), Order.Status.CONFIRMED)
        logger.info(f"Order {order.order_number} accepted by store")
        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Store owner rejects an order."""
        order = self.get_object()

        if not (request.user.is_store_owner and order.store.owner == request.user):
            return Response(
                {"error": "Only the store owner can reject orders."},
                status=status.HTTP_403_FORBIDDEN,
            )

        reason = request.data.get("reason", "Rejected by store.")

        try:
            order.transition_to(
                Order.Status.CANCELLED,
                reason=reason,
                cancelled_by="store",
            )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        DeliveryTracking.objects.create(
            order=order,
            event_type=DeliveryTracking.EventType.STATUS_CHANGE,
            status=Order.Status.CANCELLED,
            description=f"Order rejected by store: {reason}",
            created_by=request.user,
        )

        notify_order_status_change.delay(str(order.id), Order.Status.CANCELLED)
        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="update-status")
    def update_status(self, request, pk=None):
        """
        Update order status.
        Available to store owners (preparing, ready) and drivers (picked_up, en_route, delivered).
        """
        order = self.get_object()
        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]

        # Validate permissions for status transitions
        store_statuses = [Order.Status.PREPARING, Order.Status.READY]
        driver_statuses = [
            Order.Status.PICKED_UP,
            Order.Status.EN_ROUTE,
            Order.Status.DELIVERED,
        ]

        if new_status in store_statuses:
            if not (request.user.is_store_owner and order.store.owner == request.user):
                return Response(
                    {"error": "Only the store owner can set this status."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif new_status in driver_statuses:
            if not (request.user.is_driver and order.driver == request.user):
                return Response(
                    {"error": "Only the assigned driver can set this status."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            order.transition_to(new_status)
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Handle status-specific logic
        if new_status == Order.Status.READY:
            # Trigger driver assignment
            process_order_auto_assignment.delay(str(order.id))

        if new_status == Order.Status.DELIVERED:
            # Update store order count
            order.store.total_orders += 1
            order.store.save(update_fields=["total_orders"])

            # Update customer stats
            if hasattr(order.customer, "customer_profile"):
                profile = order.customer.customer_profile
                profile.total_orders += 1
                profile.total_spent += order.total_amount
                profile.add_loyalty_points(order.total_amount)
                profile.save(update_fields=["total_orders", "total_spent"])

            # Update driver stats
            if order.driver and hasattr(order.driver, "driver_profile"):
                driver_profile = order.driver.driver_profile
                delivery_time = 0
                if order.picked_up_at and order.delivered_at:
                    delivery_time = int(
                        (order.delivered_at - order.picked_up_at).total_seconds() / 60
                    )
                driver_earnings = order.delivery_fee + order.tip_amount
                driver_profile.complete_delivery(driver_earnings, delivery_time)

        DeliveryTracking.objects.create(
            order=order,
            event_type=DeliveryTracking.EventType.STATUS_CHANGE,
            status=new_status,
            description=serializer.validated_data.get("notes", f"Status updated to {new_status}"),
            created_by=request.user,
        )

        notify_order_status_change.delay(str(order.id), new_status)
        logger.info(
            f"Order {order.order_number} status updated to {new_status}"
        )
        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel an order (customer, store owner, or admin)."""
        order = self.get_object()
        reason = request.data.get("reason", "")

        # Determine who is cancelling
        if request.user == order.customer:
            cancelled_by = "customer"
        elif request.user.is_store_owner and order.store.owner == request.user:
            cancelled_by = "store"
        elif request.user.is_admin_user:
            cancelled_by = "system"
        else:
            return Response(
                {"error": "You do not have permission to cancel this order."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            order.transition_to(
                Order.Status.CANCELLED,
                reason=reason,
                cancelled_by=cancelled_by,
            )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Restore stock
        for item in order.items.all():
            if item.product:
                item.product.restore_stock(item.quantity)

        DeliveryTracking.objects.create(
            order=order,
            event_type=DeliveryTracking.EventType.STATUS_CHANGE,
            status=Order.Status.CANCELLED,
            description=f"Order cancelled by {cancelled_by}: {reason}",
            created_by=request.user,
        )

        notify_order_status_change.delay(str(order.id), Order.Status.CANCELLED)
        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=["post"])
    def rate(self, request, pk=None):
        """Rate a delivered order."""
        order = self.get_object()

        if order.customer != request.user:
            return Response(
                {"error": "Only the customer can rate this order."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if order.status != Order.Status.DELIVERED:
            return Response(
                {"error": "Can only rate delivered orders."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OrderRatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order.customer_rating = serializer.validated_data["customer_rating"]
        order.customer_feedback = serializer.validated_data.get(
            "customer_feedback", ""
        )

        # Update store rating
        order.store.update_rating(order.customer_rating)

        # Rate driver if provided
        if "driver_rating" in serializer.validated_data and order.driver:
            order.driver_rating = serializer.validated_data["driver_rating"]
            if hasattr(order.driver, "driver_profile"):
                order.driver.driver_profile.update_rating(order.driver_rating)

        order.save(
            update_fields=[
                "customer_rating",
                "customer_feedback",
                "driver_rating",
            ]
        )

        return Response(
            {"message": "Thank you for your rating!"},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def tracking(self, request, pk=None):
        """Get tracking events for an order."""
        order = self.get_object()
        events = order.tracking_events.all()
        serializer = DeliveryTracking(events, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def active(self, request):
        """Get active orders for the current user."""
        active_statuses = [
            Order.Status.PENDING,
            Order.Status.CONFIRMED,
            Order.Status.PREPARING,
            Order.Status.READY,
            Order.Status.PICKED_UP,
            Order.Status.EN_ROUTE,
        ]
        orders = self.get_queryset().filter(status__in=active_statuses)
        serializer = OrderListSerializer(orders, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="store-orders")
    def store_orders(self, request):
        """Get orders for the store owner's stores."""
        if not request.user.is_store_owner:
            return Response(
                {"error": "Only store owners can view store orders."},
                status=status.HTTP_403_FORBIDDEN,
            )

        orders = Order.objects.filter(
            store__owner=request.user
        ).select_related("customer", "driver", "store")

        status_filter = request.query_params.get("status")
        if status_filter:
            orders = orders.filter(status=status_filter)

        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = OrderListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = OrderListSerializer(orders, many=True)
        return Response(serializer.data)
