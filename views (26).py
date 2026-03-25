"""
Payment URL configuration.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"", views.PaymentViewSet, basename="payments")
router.register(r"promo-codes", views.PromoCodeViewSet, basename="promo-codes")

app_name = "payments"

urlpatterns = [
    path("webhook/stripe/", views.stripe_webhook, name="stripe-webhook"),
    path("", include(router.urls)),
]
