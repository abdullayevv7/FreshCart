"""
Celery configuration for FreshCart project.

Sets up the Celery application with Django integration, task autodiscovery,
and periodic task scheduling.
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("freshcart")

# Load configuration from Django settings with the CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all registered Django apps
app.autodiscover_tasks()

# ── Periodic Tasks (Celery Beat) ─────────────────────

app.conf.beat_schedule = {
    # Cancel orders that have been pending for too long
    "cancel-stale-orders": {
        "task": "apps.orders.tasks.cancel_stale_orders",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "orders"},
    },
    # Check for low stock and send alerts
    "check-low-stock-alerts": {
        "task": "apps.orders.tasks.check_low_stock_alerts",
        "schedule": crontab(minute=0, hour="*/2"),
        "options": {"queue": "notifications"},
    },
    # Clean up expired driver locations from Redis
    "cleanup-stale-driver-locations": {
        "task": "apps.orders.tasks.cleanup_stale_driver_locations",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "default"},
    },
    # Generate daily sales summary
    "daily-sales-summary": {
        "task": "apps.orders.tasks.generate_daily_sales_summary",
        "schedule": crontab(minute=0, hour=2),  # 2:00 AM UTC
        "options": {"queue": "default"},
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for verifying Celery connectivity."""
    print(f"Request: {self.request!r}")
