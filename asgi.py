"""
Product views for FreshCart.

Handles product listing, detail, search, reviews, and store owner management.
"""

import logging

from django.db.models import Q
from django_filters import rest_framework as django_filters
from rest_framework import filters, generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsCustomer, IsStoreOwner, IsStoreOwnerOfStore

from .models import Category, GroceryProduct, ProductImage, ProductReview, ProductVariant
from .serializers import (
    CategoryListSerializer,
    CategorySerializer,
    ProductCreateUpdateSerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductReviewSerializer,
    ProductVariantSerializer,
)

logger = logging.getLogger(__name__)


class ProductFilter(django_filters.FilterSet):
    """Custom filter for products."""

    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    store = django_filters.UUIDFilter(field_name="store__id")
    category = django_filters.UUIDFilter(field_name="category__id")
    brand = django_filters.CharFilter(field_name="brand", lookup_expr="icontains")
    dietary_tag = django_filters.CharFilter(method="filter_dietary_tag")
    on_sale = django_filters.BooleanFilter(method="filter_on_sale")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = GroceryProduct
        fields = [
            "store",
            "category",
            "brand",
            "unit",
            "is_featured",
            "is_perishable",
        ]

    def filter_dietary_tag(self, queryset, name, value):
        return queryset.filter(dietary_tags__contains=[value])

    def filter_on_sale(self, queryset, name, value):
        if value:
            return queryset.filter(
                compare_at_price__isnull=False,
                compare_at_price__gt=models.F("price"),
            )
        return queryset

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock_quantity__gt=0, is_available=True)
        return queryset


class CategoryViewSet(viewsets.ModelViewSet):
    """CRUD for product categories."""

    queryset = Category.objects.filter(is_active=True, parent__isnull=True)

    def get_serializer_class(self):
        if self.action == "list":
            return CategoryListSerializer
        return CategorySerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]


class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet for product operations.

    Customers can browse and filter products.
    Store owners can manage products for their stores.
    """

    filter_backends = [
        django_filters.DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ProductFilter
    search_fields = ["name", "description", "brand", "sku"]
    ordering_fields = ["price", "rating", "total_sold", "created_at", "name"]
    ordering = ["-is_featured", "-created_at"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ProductCreateUpdateSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "search"):
            return [permissions.AllowAny()]
        if self.action in ("create",):
            return [permissions.IsAuthenticated(), IsStoreOwner()]
        if self.action in ("update", "partial_update", "destroy"):
            return [permissions.IsAuthenticated(), IsStoreOwnerOfStore()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = GroceryProduct.objects.select_related("store", "category")

        user = self.request.user
        if user.is_authenticated and user.is_store_owner:
            if self.action in ("list",):
                return qs.filter(
                    Q(store__owner=user) | Q(is_available=True)
                ).distinct()
            if self.action in ("update", "partial_update", "destroy"):
                return qs.filter(store__owner=user)

        return qs.filter(is_available=True)

    def perform_create(self, serializer):
        """Create product, assigning to the owner's store."""
        store_id = self.request.data.get("store")
        from apps.stores.models import Store

        try:
            store = Store.objects.get(
                id=store_id, owner=self.request.user
            )
        except Store.DoesNotExist:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You can only add products to your own stores.")

        serializer.save(store=store)
        logger.info(
            f"Product created: {serializer.instance.name} in {store.name}"
        )

    @action(detail=False, methods=["get"])
    def search(self, request):
        """
        Advanced product search.

        Query params:
        - q: Search query (searches name, description, brand)
        - store: Store UUID
        - category: Category UUID
        - min_price / max_price: Price range
        - dietary_tag: Filter by dietary tag
        """
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response(
                {"error": "Search query 'q' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        products = GroceryProduct.objects.filter(
            is_available=True
        ).filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(brand__icontains=query)
            | Q(category__name__icontains=query)
        ).select_related("store", "category").order_by("-rating", "-total_sold")

        # Apply additional filters
        store_id = request.query_params.get("store")
        if store_id:
            products = products.filter(store_id=store_id)

        category_id = request.query_params.get("category")
        if category_id:
            products = products.filter(category_id=category_id)

        page = self.paginate_queryset(products)
        if page is not None:
            serializer = ProductListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"])
    def reviews(self, request, pk=None):
        """Get or create reviews for a product."""
        product = self.get_object()

        if request.method == "GET":
            reviews = product.reviews.all()
            page = self.paginate_queryset(reviews)
            if page is not None:
                serializer = ProductReviewSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = ProductReviewSerializer(reviews, many=True)
            return Response(serializer.data)

        # POST - create a review
        if not request.user.is_authenticated or not request.user.is_customer:
            return Response(
                {"error": "Only customers can leave reviews."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check for existing review
        if ProductReview.objects.filter(
            product=product, customer=request.user
        ).exists():
            return Response(
                {"error": "You have already reviewed this product."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ProductReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Check if user has actually purchased this product
        from apps.orders.models import OrderItem

        is_verified = OrderItem.objects.filter(
            order__customer=request.user,
            product=product,
            order__status="delivered",
        ).exists()

        serializer.save(
            product=product,
            customer=request.user,
            is_verified_purchase=is_verified,
        )

        # Update product rating
        product.update_rating(serializer.validated_data["rating"])

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def featured(self, request):
        """Get featured products."""
        products = GroceryProduct.objects.filter(
            is_available=True, is_featured=True
        ).select_related("store", "category")[:20]
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def on_sale(self, request):
        """Get products currently on sale."""
        from django.db.models import F

        products = (
            GroceryProduct.objects.filter(
                is_available=True,
                compare_at_price__isnull=False,
                compare_at_price__gt=F("price"),
            )
            .select_related("store", "category")
            .order_by("-created_at")[:20]
        )
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)


class StoreProductsView(generics.ListAPIView):
    """List all products for a specific store."""

    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "brand"]
    ordering_fields = ["price", "rating", "name"]

    def get_queryset(self):
        store_id = self.kwargs["store_id"]
        return GroceryProduct.objects.filter(
            store_id=store_id, is_available=True
        ).select_related("category")
