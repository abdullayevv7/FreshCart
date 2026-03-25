"""
Account URL configuration.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

router = DefaultRouter()
router.register(r"admin/users", views.AdminUserViewSet, basename="admin-users")
router.register(r"addresses", views.DeliveryAddressViewSet, basename="delivery-addresses")

app_name = "accounts"

urlpatterns = [
    # Authentication
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.CustomTokenObtainPairView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    # Profile
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/change-password/", views.ChangePasswordView.as_view(), name="change-password"),
    path("profile/customer/", views.CustomerProfileView.as_view(), name="customer-profile"),
    path("profile/store-owner/", views.StoreOwnerProfileView.as_view(), name="store-owner-profile"),
    path("profile/driver/", views.DriverProfileView.as_view(), name="driver-profile"),
    path("profile/driver/availability/", views.DriverAvailabilityView.as_view(), name="driver-availability"),
    # Router URLs
    path("", include(router.urls)),
]
