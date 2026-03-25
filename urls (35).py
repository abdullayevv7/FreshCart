"""
Store views for FreshCart.

Handles store CRUD, nearby store search, and store analytics.
"""

import logging
from decimal import Decimal

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAdmin, IsStoreOwner, IsStoreOwnerOfStore

from .models import OperatingHours, Store, StoreCategory
from .serializers import (
    StoreAnalyticsSerializer,
    StoreCategorySerializer,
    StoreCreateUpdateSerializer,
    StoreDetailSerializer,
    StoreListSerializer,
)

logger = logging.getLogger(__name__)


class StoreCategoryViewSet(viewsets.ModelViewSet):
    """CRUD for store categories. Read for all, write for admins."""

    queryset = StoreCategory.objects.filter(is_active=True)
    serializer_class = StoreCategorySerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsAdmin()]


class StoreViewSet(viewsets.ModelViewSet):
    """
    ViewSet for store operations.

    - Customers: Can list and view active stores
    - Store Owners: Can create and manage their own stores
    - Admins: Full access to all stores
    """

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category", "city", "status", "is_featured"]
    search_fields = ["name", "description", "city"]
    ordering_fields = ["rating", "total_orders", "created_at", "name"]
    ordering = ["-is_featured", "-rating"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return StoreCreateUpdateSerializer
        if self.action == "retrieve":
            return StoreDetailSerializer
        return StoreListSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "nearby"):
            return [permissions.AllowAny()]
        if self.action in ("create",):
            return [permissions.IsAuthenticated(), IsStoreOwner()]
        if self.action in ("update", "partial_update", "destroy", "analytics"):
            return [permissions.IsAuthenticated(), IsStoreOwnerOfStore()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = Store.objects.select_related("category", "owner")

        # Store owners see their own stores regardless of status
        if user.is_authenticated and user.is_store_owner:
            if self.action in ("list",):
                return qs.filter(
                    Q(owner=user) | Q(status=Store.Status.ACTIVE)
                ).distinct()
            return qs.filter(owner=user)

        # Admins see everything
        if user.is_authenticated and (user.is_admin_user or user.is_superuser):
            return qs

        # Everyone else sees only active stores
        return qs.filter(status=Store.Status.ACTIVE)

    def perform_create(self, serializer):
        """Set the owner to the current user and geocode the address."""
        from django.contrib.gis.geos import Point

        store = serializer.save(owner=self.request.user)

        # Attempt geocoding from address
        try:
            from utils.geo import geocode_address

            address = (
                f"{store.address_line_1}, {store.city}, "
                f"{store.state} {store.postal_code}"
            )
            coords = geocode_address(address)
            if coords:
                store.location = Point(coords["longitude"], coords["latitude"])
                store.save(update_fields=["location"])
        except Exception as e:
            logger.warning(f"Geocoding failed for store {store.name}: {e}")

        logger.info(f"Store created: {store.name} by {self.request.user.email}")

    @action(detail=False, methods=["get"])
    def nearby(self, request):
        """
        Find stores near a given location.

        Query params:
        - lat: Latitude (required)
        - lng: Longitude (required)
        - radius: Search radius in km (default: 15)
        """
        lat = request.query_params.get("lat")
        lng = request.query_params.get("lng")
        radius = float(request.query_params.get("radius", 15))

        if not lat or not lng:
            return Response(
                {"error": "Both 'lat' and 'lng' query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_location = Point(float(lng), float(lat), srid=4326)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid latitude or longitude values."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stores = (
            Store.objects.filter(
                status=Store.Status.ACTIVE,
                location__distance_lte=(user_location, D(km=radius)),
            )
            .annotate(distance=Distance("location", user_location))
            .order_by("distance")
            .select_related("category")
        )

        serializer = StoreListSerializer(stores, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def analytics(self, request, pk=None):
        """Get analytics data for a store (store owner only)."""
        store = self.get_object()
        today = timezone.now().date()

        orders = store.orders.all()
        orders_today = orders.filter(created_at__date=today)

        # Aggregate data
        total_revenue = (
            orders.filter(status="delivered").aggregate(
                total=Sum("total_amount")
            )["total"]
            or Decimal("0.00")
        )
        revenue_today = (
            orders_today.filter(status="delivered").aggregate(
                total=Sum("total_amount")
            )["total"]
            or Decimal("0.00")
        )
        avg_order = (
            orders.filter(status="delivered").aggregate(
                avg=Avg("total_amount")
            )["avg"]
            or Decimal("0.00")
        )

        # Popular products (top 10 by order count)
        from apps.orders.models import OrderItem

        popular = (
            OrderItem.objects.filter(order__store=store)
            .values("product__name")
            .annotate(order_count=Count("id"), total_qty=Sum("quantity"))
            .order_by("-order_count")[:10]
        )

        # Orders by status
        status_counts = dict(
            orders.values_list("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        data = {
            "total_orders": store.total_orders,
            "total_revenue": total_revenue,
            "average_order_value": round(avg_order, 2),
            "orders_today": orders_today.count(),
            "revenue_today": revenue_today,
            "popular_products": list(popular),
            "orders_by_status": status_counts,
            "rating": store.rating,
            "total_ratings": store.total_ratings,
        }

        return Response(StoreAnalyticsSerializer(data).data)

    @action(detail=True, methods=["get"])
    def operating_hours(self, request, pk=None):
        """Get operating hours for a store."""
        store = self.get_object()
        hours = store.operating_hours.all()
        from .serializers import OperatingHoursSerializer

        return Response(OperatingHoursSerializer(hours, many=True).data)


class MyStoresView(generics.ListAPIView):
    """List stores owned by the authenticated store owner."""

    serializer_class = StoreDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwner]

    def get_queryset(self):
        return Store.objects.filter(owner=self.request.user).select_related(
            "category"
        )
