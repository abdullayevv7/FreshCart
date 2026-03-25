"""
Geographic utility functions for FreshCart.

Provides distance calculations, geocoding, and delivery zone
lookups used across orders, stores, and delivery modules.
"""

import logging
import math
from decimal import Decimal

from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D

logger = logging.getLogger(__name__)


def calculate_distance(point_a, point_b):
    """
    Calculate the distance between two geographic points in kilometers.

    Uses PostGIS distance calculation when available, falls back to
    the Haversine formula for non-GIS environments.

    Args:
        point_a: django.contrib.gis.geos.Point (lon, lat)
        point_b: django.contrib.gis.geos.Point (lon, lat)

    Returns:
        float: Distance in kilometers
    """
    if point_a is None or point_b is None:
        return 0.0

    try:
        # Use PostGIS native distance (most accurate)
        distance_m = point_a.distance(point_b)
        # PostGIS returns degrees for geography=True, convert to km
        # 1 degree of latitude is approximately 111.32 km
        distance_km = distance_m * 111.32
        return round(distance_km, 2)
    except Exception:
        # Fall back to Haversine formula
        return _haversine_distance(
            point_a.y, point_a.x,  # lat, lon
            point_b.y, point_b.x,
        )


def _haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points
    on the Earth using the Haversine formula.

    Args:
        lat1, lon1: Latitude and longitude of point 1 (in degrees)
        lat2, lon2: Latitude and longitude of point 2 (in degrees)

    Returns:
        float: Distance in kilometers
    """
    EARTH_RADIUS_KM = 6371.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = EARTH_RADIUS_KM * c
    return round(distance, 2)


def geocode_address(address):
    """
    Convert an address string to geographic coordinates.

    Uses a geocoding API to resolve addresses. Returns None if
    the address cannot be geocoded.

    Args:
        address: str, full address string

    Returns:
        dict with 'latitude' and 'longitude' keys, or None
    """
    try:
        import requests

        api_key = getattr(settings, "GEOCODING_API_KEY", "")

        if not api_key:
            logger.warning("Geocoding API key not configured, using fallback.")
            return _fallback_geocode(address)

        response = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={
                "address": address,
                "key": api_key,
            },
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "OK" and data.get("results"):
            location = data["results"][0]["geometry"]["location"]
            return {
                "latitude": location["lat"],
                "longitude": location["lng"],
            }

        logger.warning(f"Geocoding returned no results for: {address}")
        return None

    except ImportError:
        logger.warning("requests library not available for geocoding.")
        return _fallback_geocode(address)
    except Exception as e:
        logger.error(f"Geocoding failed for '{address}': {e}")
        return None


def _fallback_geocode(address):
    """
    Fallback geocoding that returns approximate US city coordinates.
    Used when no geocoding API is configured.
    """
    CITY_COORDS = {
        "new york": {"latitude": 40.7128, "longitude": -74.0060},
        "los angeles": {"latitude": 34.0522, "longitude": -118.2437},
        "chicago": {"latitude": 41.8781, "longitude": -87.6298},
        "houston": {"latitude": 29.7604, "longitude": -95.3698},
        "phoenix": {"latitude": 33.4484, "longitude": -112.0740},
        "san francisco": {"latitude": 37.7749, "longitude": -122.4194},
        "seattle": {"latitude": 47.6062, "longitude": -122.3321},
        "miami": {"latitude": 25.7617, "longitude": -80.1918},
        "boston": {"latitude": 42.3601, "longitude": -71.0589},
        "denver": {"latitude": 39.7392, "longitude": -104.9903},
    }

    address_lower = address.lower()
    for city, coords in CITY_COORDS.items():
        if city in address_lower:
            return coords

    # Default to a central US location
    return {"latitude": 39.8283, "longitude": -98.5795}


def calculate_delivery_fee(distance_km, store=None, zone=None):
    """
    Calculate delivery fee based on distance, store config, and zone config.

    Priority:
    1. Delivery zone pricing (if zone provided)
    2. Store-specific pricing (if store provided)
    3. Platform default pricing

    Args:
        distance_km: float, delivery distance in km
        store: Store model instance (optional)
        zone: DeliveryZone model instance (optional)

    Returns:
        Decimal: calculated delivery fee
    """
    if zone:
        fee = zone.calculate_delivery_fee(distance_km)
        return Decimal(str(fee))

    if store:
        # Check if order qualifies for free delivery
        if (
            store.free_delivery_threshold
            and store.delivery_fee <= 0
        ):
            return Decimal("0.00")

        fee = store.calculate_delivery_fee(distance_km)
        return Decimal(str(fee))

    # Platform defaults
    base_fee = Decimal(str(
        settings.FRESHCART.get("BASE_DELIVERY_FEE", 2.99)
    ))
    per_km_fee = Decimal(str(
        settings.FRESHCART.get("DELIVERY_FEE_PER_KM", 1.50)
    ))

    total = base_fee + (per_km_fee * Decimal(str(distance_km)))
    return round(total, 2)


def find_delivery_zone(latitude, longitude):
    """
    Find the delivery zone that contains the given coordinates.

    Args:
        latitude: float
        longitude: float

    Returns:
        DeliveryZone instance or None
    """
    from apps.delivery.models import DeliveryZone

    point = Point(longitude, latitude, srid=4326)

    zone = DeliveryZone.objects.filter(
        is_active=True,
        boundary__contains=point,
    ).first()

    return zone


def is_within_delivery_radius(store, delivery_point):
    """
    Check if a delivery point is within a store's delivery radius.

    Args:
        store: Store model instance
        delivery_point: Point (lon, lat)

    Returns:
        bool
    """
    if not store.location or not delivery_point:
        return False

    distance = calculate_distance(store.location, delivery_point)
    return distance <= store.delivery_radius_km


def find_nearest_stores(latitude, longitude, radius_km=15, limit=20):
    """
    Find stores nearest to a given location.

    Args:
        latitude: float
        longitude: float
        radius_km: float, search radius in km
        limit: int, maximum number of stores to return

    Returns:
        QuerySet of Store objects annotated with distance
    """
    from django.contrib.gis.db.models.functions import Distance

    from apps.stores.models import Store

    user_location = Point(longitude, latitude, srid=4326)

    stores = (
        Store.objects.filter(
            status=Store.Status.ACTIVE,
            location__distance_lte=(user_location, D(km=radius_km)),
        )
        .annotate(distance=Distance("location", user_location))
        .order_by("distance")
        .select_related("category")[:limit]
    )

    return stores
