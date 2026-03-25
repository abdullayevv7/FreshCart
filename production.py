"""
Store URL configuration.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"categories", views.StoreCategoryViewSet, basename="store-categories")
router.register(r"", views.StoreViewSet, basename="stores")

app_name = "stores"

urlpatterns = [
    path("my-stores/", views.MyStoresView.as_view(), name="my-stores"),
    path("", include(router.urls)),
]
