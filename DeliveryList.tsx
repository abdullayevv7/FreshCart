version: "3.9"

services:
  # ──────────────────────────────────────────────
  # PostgreSQL + PostGIS
  # ──────────────────────────────────────────────
  db:
    image: postgis/postgis:15-3.3
    container_name: freshcart_db
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-freshcart}
      POSTGRES_USER: ${POSTGRES_USER:-freshcart}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-freshcart_secret}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-freshcart}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - freshcart_network

  # ──────────────────────────────────────────────
  # Redis (cache + Celery broker + Channels layer)
  # ──────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    container_name: freshcart_redis
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "${REDIS_PORT:-6379}:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - freshcart_network

  # ──────────────────────────────────────────────
  # Django Backend (ASGI via Daphne)
  # ──────────────────────────────────────────────
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: freshcart_backend
    restart: unless-stopped
    command: >
      bash -c "
        python manage.py migrate --noinput &&
        python manage.py collectstatic --noinput &&
        daphne -b 0.0.0.0 -p 8000 config.asgi:application
      "
    environment:
      - DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-config.settings.production}
      - DATABASE_URL=postgis://${POSTGRES_USER:-freshcart}:${POSTGRES_PASSWORD:-freshcart_secret}@db:5432/${POSTGRES_DB:-freshcart}
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
      - SECRET_KEY=${SECRET_KEY}
      - DEBUG=${DEBUG:-False}
      - ALLOWED_HOSTS=${ALLOWED_HOSTS:-*}
      - CORS_ALLOWED_ORIGINS=${CORS_ALLOWED_ORIGINS:-http://localhost:8080}
      - STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY:-}
      - STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET:-}
      - EMAIL_HOST=${EMAIL_HOST:-smtp.gmail.com}
      - EMAIL_PORT=${EMAIL_PORT:-587}
      - EMAIL_HOST_USER=${EMAIL_HOST_USER:-}
      - EMAIL_HOST_PASSWORD=${EMAIL_HOST_PASSWORD:-}
    volumes:
      - ./backend:/app
      - backend_static:/app/staticfiles
      - backend_media:/app/media
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - freshcart_network

  # ──────────────────────────────────────────────
  # Celery Worker
  # ──────────────────────────────────────────────
  celery_worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: freshcart_celery_worker
    restart: unless-stopped
    command: celery -A config worker -l info --concurrency=4 -Q default,orders,notifications
    environment:
      - DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-config.settings.production}
      - DATABASE_URL=postgis://${POSTGRES_USER:-freshcart}:${POSTGRES_PASSWORD:-freshcart_secret}@db:5432/${POSTGRES_DB:-freshcart}
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
      - SECRET_KEY=${SECRET_KEY}
    volumes:
      - ./backend:/app
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - freshcart_network

  # ──────────────────────────────────────────────
  # Celery Beat (periodic tasks)
  # ──────────────────────────────────────────────
  celery_beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: freshcart_celery_beat
    restart: unless-stopped
    command: celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    environment:
      - DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-config.settings.production}
      - DATABASE_URL=postgis://${POSTGRES_USER:-freshcart}:${POSTGRES_PASSWORD:-freshcart_secret}@db:5432/${POSTGRES_DB:-freshcart}
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
      - SECRET_KEY=${SECRET_KEY}
    volumes:
      - ./backend:/app
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - freshcart_network

  # ──────────────────────────────────────────────
  # Vue.js Frontend
  # ──────────────────────────────────────────────
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: freshcart_frontend
    restart: unless-stopped
    environment:
      - VUE_APP_API_URL=${VUE_APP_API_URL:-http://localhost:8000/api/v1}
      - VUE_APP_WS_URL=${VUE_APP_WS_URL:-ws://localhost:8000/ws}
    volumes:
      - ./frontend:/app
      - /app/node_modules
    ports:
      - "8080:8080"
    depends_on:
      - backend
    networks:
      - freshcart_network

  # ──────────────────────────────────────────────
  # Nginx Reverse Proxy
  # ──────────────────────────────────────────────
  nginx:
    image: nginx:1.25-alpine
    container_name: freshcart_nginx
    restart: unless-stopped
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - backend_static:/var/www/static:ro
      - backend_media:/var/www/media:ro
    ports:
      - "${NGINX_PORT:-80}:80"
      - "${NGINX_SSL_PORT:-443}:443"
    depends_on:
      - backend
      - frontend
    networks:
      - freshcart_network

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  backend_static:
    driver: local
  backend_media:
    driver: local

networks:
  freshcart_network:
    driver: bridge
