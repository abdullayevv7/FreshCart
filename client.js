# Django core
Django==4.2.11
djangorestframework==3.14.0
django-cors-headers==4.3.1
django-filter==23.5
django-extensions==3.2.3

# Authentication
djangorestframework-simplejwt==5.3.1
PyJWT==2.8.0

# Database
psycopg2-binary==2.9.9
dj-database-url==2.1.0

# Geospatial
# Requires GDAL system library
# django.contrib.gis is built into Django

# Async / WebSocket
channels==4.0.0
channels-redis==4.1.0
daphne==4.0.0

# Celery
celery==5.3.6
django-celery-beat==2.5.0
django-celery-results==2.5.1
redis==5.0.1

# Payments
stripe==7.12.0

# File handling
Pillow==10.2.0

# Utilities
python-decouple==3.8
gunicorn==21.1.0
whitenoise==6.6.0
django-storages==1.14.2

# Serialization helpers
drf-writable-nested==0.7.0

# API documentation
drf-spectacular==0.27.1

# Development and testing
pytest==8.0.0
pytest-django==4.8.0
pytest-cov==4.1.0
factory-boy==3.3.0
faker==22.6.0
flake8==7.0.0
black==24.1.1
isort==5.13.2

# Monitoring
sentry-sdk==1.40.4

# Math / geospatial utilities
geopy==2.4.1
