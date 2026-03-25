"""
Custom exception handling for FreshCart REST API.

Provides a standardized error response format across the platform
and centralizes error logging for easier debugging.
"""

import logging

from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied as DRFPermissionDenied,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that wraps DRF's default handler to provide:
    - Consistent error response structure
    - Detailed logging for server errors
    - Human-readable error messages

    Response format:
    {
        "error": true,
        "message": "A human-readable error summary",
        "errors": { ... } or [...],  // detailed validation errors
        "status_code": 400
    }
    """
    # Get the standard DRF response first
    response = exception_handler(exc, context)

    # If DRF didn't handle it, it's an unhandled server error
    if response is None:
        if isinstance(exc, DjangoValidationError):
            # Django model-level validation errors
            data = {
                "error": True,
                "message": "Validation error.",
                "errors": exc.message_dict if hasattr(exc, "message_dict") else exc.messages,
                "status_code": status.HTTP_400_BAD_REQUEST,
            }
            response = Response(data, status=status.HTTP_400_BAD_REQUEST)
        elif isinstance(exc, Http404):
            data = {
                "error": True,
                "message": "Resource not found.",
                "status_code": status.HTTP_404_NOT_FOUND,
            }
            response = Response(data, status=status.HTTP_404_NOT_FOUND)
        elif isinstance(exc, PermissionDenied):
            data = {
                "error": True,
                "message": "You do not have permission to perform this action.",
                "status_code": status.HTTP_403_FORBIDDEN,
            }
            response = Response(data, status=status.HTTP_403_FORBIDDEN)
        else:
            # Unexpected server error - log the full traceback
            view = context.get("view")
            view_name = view.__class__.__name__ if view else "UnknownView"
            logger.exception(
                f"Unhandled exception in {view_name}: {exc.__class__.__name__}: {exc}"
            )
            data = {
                "error": True,
                "message": "An unexpected error occurred. Please try again later.",
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            }
            response = Response(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return response

    # Format the DRF response into our standard structure
    error_data = {
        "error": True,
        "status_code": response.status_code,
    }

    if isinstance(exc, ValidationError):
        error_data["message"] = "Validation error."
        error_data["errors"] = response.data
    elif isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        error_data["message"] = _extract_message(
            response.data, "Authentication credentials were not provided or are invalid."
        )
    elif isinstance(exc, DRFPermissionDenied):
        error_data["message"] = _extract_message(
            response.data, "You do not have permission to perform this action."
        )
    elif isinstance(exc, APIException):
        error_data["message"] = _extract_message(
            response.data, str(exc.detail) if hasattr(exc, "detail") else "An error occurred."
        )
    else:
        error_data["message"] = _extract_message(response.data, "An error occurred.")

    # Log 5xx errors with full context
    if response.status_code >= 500:
        view = context.get("view")
        view_name = view.__class__.__name__ if view else "UnknownView"
        logger.error(
            f"Server error in {view_name}: {response.status_code} - {error_data['message']}"
        )

    response.data = error_data
    return response


def _extract_message(data, default="An error occurred."):
    """
    Extract a human-readable message from DRF error data.
    DRF may return strings, lists, or dicts.
    """
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return data[0] if data else default
    if isinstance(data, dict):
        # Try common keys first
        for key in ("detail", "message", "error", "non_field_errors"):
            if key in data:
                val = data[key]
                if isinstance(val, list):
                    return val[0] if val else default
                return str(val)
        # Fall back to first error value
        for key, val in data.items():
            if isinstance(val, list) and val:
                return f"{key}: {val[0]}"
            if isinstance(val, str):
                return f"{key}: {val}"
    return default


class ServiceUnavailable(APIException):
    """Raised when an external service (Stripe, geocoding, etc.) is unavailable."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Service temporarily unavailable. Please try again later."
    default_code = "service_unavailable"


class PaymentError(APIException):
    """Raised when a payment processing error occurs."""

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "Payment processing failed."
    default_code = "payment_error"


class DeliveryUnavailable(APIException):
    """Raised when delivery is not available for the given location."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Delivery is not available for this location."
    default_code = "delivery_unavailable"


class OrderTransitionError(APIException):
    """Raised when an invalid order status transition is attempted."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This status transition is not allowed."
    default_code = "invalid_transition"
