"""
Product URL configuration.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"categories", views.CategoryViewSet, basename="categories")
router.register(r"", views.ProductViewSet, basename="products")

app_name = "products"

urlpatterns = [
    path(
        "store/<uuid:store_id>/",
        views.StoreProductsView.as_view(),
        name="store-products",
    ),
    path("", include(router.urls)),
]
