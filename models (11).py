"""
Delivery URL configuration.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"zones", views.DeliveryZoneViewSet, basename="delivery-zones")

app_name = "delivery"

urlpatterns = [
    # Driver location updates
    path(
        "location/update/",
        views.DriverLocationUpdateView.as_view(),
        name="driver-location-update",
    ),
    # Active delivery for current driver
    path(
        "active/",
        views.ActiveDeliveryView.as_view(),
        name="active-delivery",
    ),
    # Accept or decline a delivery assignment
    path(
        "assignment/<uuid:order_id>/",
        views.DeliveryAssignmentView.as_view(),
        name="delivery-assignment",
    ),
    # Driver delivery history
    path(
        "history/",
        views.DriverDeliveryHistoryView.as_view(),
        name="delivery-history",
    ),
    # Driver earnings
    path(
        "earnings/",
        views.DriverEarningsView.as_view(),
        name="driver-earnings",
    ),
    # Router URLs
    path("", include(router.urls)),
]
