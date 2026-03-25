# FreshCart - Grocery Delivery Platform

A full-stack, production-grade grocery delivery platform that connects customers with local grocery stores and provides real-time delivery tracking. Built with Django, Vue.js, PostgreSQL, Redis, Celery, and WebSockets.

---

## Table of Contents

- [Project Description](#project-description)
- [Goal](#goal)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Folder Structure](#folder-structure)
- [User Roles](#user-roles)
- [Business Logic](#business-logic)
- [Setup Instructions](#setup-instructions)
- [API Documentation](#api-documentation)
- [Roadmap](#roadmap)
- [Improvements](#improvements)

---

## Project Description

FreshCart is a comprehensive grocery delivery platform designed to serve four distinct user roles: customers, store owners, delivery drivers, and administrators. Customers can browse local grocery stores, add products to their cart, place orders, and track deliveries in real time on a live map. Store owners manage their inventories, accept or reject orders, and view sales analytics. Delivery drivers receive order assignments, update their location in real time via WebSocket, and manage their delivery workflow. Administrators oversee the entire platform through a dedicated admin panel.

The platform is engineered for production use with Docker containerization, Celery for background task processing, Redis for caching and WebSocket channel layers, and PostgreSQL with PostGIS extensions for geospatial queries such as finding nearby stores and computing delivery distances.

---

## Goal

To provide a reliable, scalable, and user-friendly grocery delivery service that supports the complete order lifecycle -- from product browsing and cart management, through payment processing and order fulfillment, to real-time delivery tracking and order completion. The system prioritizes data integrity, low latency for real-time features, and a clean separation of concerns across all layers.

---

## Features

### Customer Features
- Browse local grocery stores filtered by distance, category, and rating
- Search and filter products by name, category, price range, and dietary tags
- Shopping cart with persistent state (synced to backend for logged-in users)
- Multiple delivery address management with geocoding
- Real-time order status updates via WebSocket
- Live delivery tracking on an interactive map
- Order history with reorder functionality
- Product reviews and ratings

### Store Owner Features
- Store profile management (hours, categories, delivery zones)
- Full product catalog management (CRUD, variants, images, stock levels)
- Incoming order queue with accept/reject workflow
- Sales analytics dashboard (revenue, popular products, peak hours)
- Inventory alerts for low-stock products
- Operating hours and holiday schedule management

### Delivery Driver Features
- Real-time order assignment notifications
- Turn-by-turn navigation integration
- Delivery status workflow (picked up, en route, delivered)
- Continuous GPS location broadcasting via WebSocket
- Earnings dashboard and delivery history
- Availability toggle (online/offline status)

### Admin Features
- Platform-wide analytics and reporting
- User management (approve/suspend accounts)
- Store verification and approval workflow
- Delivery zone configuration
- Commission and fee structure management
- System health monitoring

### Technical Features
- JWT-based authentication with token refresh
- Role-based access control with granular permissions
- Real-time WebSocket communication for tracking and notifications
- Background task processing with Celery (order timeouts, notifications, analytics)
- Geospatial queries with PostGIS (nearby stores, delivery radius)
- Paginated and filterable REST API
- Docker containerization for all services
- Nginx reverse proxy with SSL termination support

---

## Architecture

```
                                    +-------------------+
                                    |   Nginx (Proxy)   |
                                    +--------+----------+
                                             |
                          +------------------+------------------+
                          |                                     |
                +---------v----------+             +-----------v-----------+
                | Vue.js Frontend    |             | Django Backend (API)  |
                | (SPA on port 8080) |             | (DRF on port 8000)   |
                +--------------------+             +-----+-----+----------+
                                                         |     |
                                          +--------------+     +----------------+
                                          |                                     |
                                +---------v----------+             +-----------v-----------+
                                |   PostgreSQL       |             |   Redis               |
                                |   (+ PostGIS)      |             |   (Cache + Channels)  |
                                |   Port 5432        |             |   Port 6379           |
                                +--------------------+             +-----------+-----------+
                                                                               |
                                                                   +-----------v-----------+
                                                                   |   Celery Workers      |
                                                                   |   + Celery Beat       |
                                                                   +-----------------------+

WebSocket Flow:
  Browser <--WS--> Nginx <--WS--> Daphne (ASGI) <--Channel Layer--> Redis
```

---

## Tech Stack

| Layer          | Technology                             |
|----------------|----------------------------------------|
| Backend        | Python 3.11, Django 4.2, DRF 3.14      |
| Frontend       | Vue.js 3, Vuex 4, Vue Router 4         |
| Database       | PostgreSQL 15 with PostGIS 3.3          |
| Cache/Broker   | Redis 7                                |
| Task Queue     | Celery 5.3 with Celery Beat            |
| WebSocket      | Django Channels 4, Daphne              |
| Reverse Proxy  | Nginx 1.25                             |
| Containerization | Docker, Docker Compose               |
| Authentication | JWT (Simple JWT)                       |
| Geospatial     | PostGIS, GeoDjango                     |
| Maps (Frontend)| Leaflet.js                             |

---

## Folder Structure

```
freshcart/
|-- docker-compose.yml
|-- .env.example
|-- .gitignore
|-- Makefile
|-- README.md
|-- nginx/
|   |-- nginx.conf
|-- backend/
|   |-- manage.py
|   |-- requirements.txt
|   |-- config/
|   |   |-- __init__.py
|   |   |-- settings/
|   |   |   |-- __init__.py
|   |   |   |-- base.py
|   |   |   |-- development.py
|   |   |   |-- production.py
|   |   |-- urls.py
|   |   |-- wsgi.py
|   |   |-- asgi.py
|   |   |-- celery.py
|   |   |-- routing.py
|   |-- apps/
|   |   |-- __init__.py
|   |   |-- accounts/
|   |   |   |-- __init__.py
|   |   |   |-- models.py
|   |   |   |-- serializers.py
|   |   |   |-- views.py
|   |   |   |-- urls.py
|   |   |   |-- permissions.py
|   |   |   |-- admin.py
|   |   |-- stores/
|   |   |   |-- __init__.py
|   |   |   |-- models.py
|   |   |   |-- serializers.py
|   |   |   |-- views.py
|   |   |   |-- urls.py
|   |   |   |-- admin.py
|   |   |-- products/
|   |   |   |-- __init__.py
|   |   |   |-- models.py
|   |   |   |-- serializers.py
|   |   |   |-- views.py
|   |   |   |-- urls.py
|   |   |   |-- admin.py
|   |   |-- orders/
|   |   |   |-- __init__.py
|   |   |   |-- models.py
|   |   |   |-- serializers.py
|   |   |   |-- views.py
|   |   |   |-- urls.py
|   |   |   |-- admin.py
|   |   |   |-- tasks.py
|   |   |   |-- consumers.py
|   |   |-- delivery/
|   |   |   |-- __init__.py
|   |   |   |-- models.py
|   |   |   |-- serializers.py
|   |   |   |-- views.py
|   |   |   |-- urls.py
|   |   |   |-- consumers.py
|   |   |-- payments/
|   |   |   |-- __init__.py
|   |   |   |-- models.py
|   |   |   |-- services.py
|   |   |   |-- views.py
|   |   |   |-- urls.py
|   |-- utils/
|       |-- __init__.py
|       |-- pagination.py
|       |-- geo.py
|       |-- exceptions.py
|-- frontend/
    |-- package.json
    |-- public/
    |   |-- index.html
    |-- src/
        |-- main.js
        |-- App.vue
        |-- router/
        |   |-- index.js
        |-- store/
        |   |-- index.js
        |   |-- modules/
        |       |-- auth.js
        |       |-- cart.js
        |       |-- orders.js
        |-- api/
        |   |-- client.js
        |   |-- auth.js
        |   |-- products.js
        |   |-- orders.js
        |   |-- stores.js
        |-- components/
        |   |-- layout/
        |   |   |-- AppHeader.vue
        |   |   |-- AppFooter.vue
        |   |-- products/
        |   |   |-- GroceryCard.vue
        |   |   |-- CategoryFilter.vue
        |   |-- cart/
        |   |   |-- CartSidebar.vue
        |   |-- delivery/
        |   |   |-- DeliveryTracker.vue
        |   |   |-- LiveMap.vue
        |   |-- auth/
        |       |-- LoginForm.vue
        |       |-- RegisterForm.vue
        |-- views/
            |-- HomePage.vue
            |-- StorePage.vue
            |-- ProductsPage.vue
            |-- CheckoutPage.vue
            |-- OrderTrackingPage.vue
            |-- DriverDashboard.vue
            |-- StoreOwnerDashboard.vue
            |-- AdminPanel.vue
```

---

## User Roles

### 1. Customer
- **Registration:** Email/password sign-up with email verification
- **Capabilities:** Browse stores, search products, manage cart, place orders, track deliveries, leave reviews, manage delivery addresses
- **Restrictions:** Cannot access store management or driver features

### 2. Store Owner
- **Registration:** Sign-up followed by admin approval process
- **Capabilities:** Manage store profile, manage product catalog, process incoming orders (accept/reject), view sales analytics, set operating hours and delivery zones
- **Restrictions:** Can only manage their own store(s)

### 3. Delivery Driver
- **Registration:** Sign-up with document verification (license, vehicle info)
- **Capabilities:** Toggle availability, receive and accept delivery assignments, update delivery status, broadcast GPS location, view earnings history
- **Restrictions:** Cannot modify store data or place customer orders

### 4. Admin
- **Access:** Superuser accounts created via Django management command
- **Capabilities:** Full platform oversight, user management, store approval, delivery zone configuration, commission management, system analytics
- **Restrictions:** None (full access)

---

## Business Logic

### Order Lifecycle

```
1. PENDING      -- Customer places order, payment is authorized
2. CONFIRMED    -- Store owner accepts the order
3. PREPARING    -- Store begins preparing the order
4. READY        -- Order is packed and ready for pickup
5. PICKED_UP    -- Driver picks up the order from the store
6. EN_ROUTE     -- Driver is en route to customer (live tracking active)
7. DELIVERED    -- Driver confirms delivery, payment is captured
8. CANCELLED    -- Order cancelled (by customer, store, or system timeout)
```

### Pricing Logic
- **Product Price:** Base price set by store owner
- **Delivery Fee:** Calculated based on distance between store and delivery address (using PostGIS)
- **Service Fee:** Percentage-based platform commission (configurable by admin)
- **Tax:** Calculated based on delivery address jurisdiction
- **Discounts:** Promo code support with validation rules (min order, expiry, usage limits)

### Delivery Assignment
1. When an order reaches READY status, the system searches for available drivers within the store's delivery zone
2. Drivers are ranked by proximity to the store (using real-time GPS data from Redis)
3. The nearest available driver receives a WebSocket notification
4. If the driver does not accept within 60 seconds, the assignment moves to the next driver
5. If no driver accepts, the order is flagged for manual admin intervention

### Inventory Management
- Stock levels are decremented when an order is confirmed
- Stock is restored if an order is cancelled
- Low-stock alerts are sent to store owners when inventory drops below a configurable threshold
- Out-of-stock products are automatically hidden from customer search results

---

## Setup Instructions

### Prerequisites
- Docker and Docker Compose installed
- Git

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/freshcart.git
cd freshcart

# 2. Copy environment file and configure
cp .env.example .env
# Edit .env with your settings (database credentials, secret key, etc.)

# 3. Build and start all services
make build
make up

# 4. Run database migrations
make migrate

# 5. Create a superuser (admin)
make superuser

# 6. Seed sample data (optional, for development)
make seed

# The application is now available at:
# - Frontend: http://localhost:8080
# - Backend API: http://localhost:8000/api/v1/
# - Admin Panel: http://localhost:8000/admin/
```

### Manual Setup (without Docker)

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# Frontend
cd frontend
npm install
npm run serve

# Redis (required for Celery and WebSocket)
redis-server

# Celery Worker
cd backend
celery -A config worker -l info

# Celery Beat
cd backend
celery -A config beat -l info
```

---

## API Documentation

### Authentication

| Method | Endpoint                        | Description              |
|--------|---------------------------------|--------------------------|
| POST   | `/api/v1/auth/register/`        | Register new user        |
| POST   | `/api/v1/auth/login/`           | Obtain JWT token pair    |
| POST   | `/api/v1/auth/token/refresh/`   | Refresh access token     |
| GET    | `/api/v1/auth/profile/`         | Get current user profile |
| PUT    | `/api/v1/auth/profile/`         | Update user profile      |

### Stores

| Method | Endpoint                        | Description              |
|--------|---------------------------------|--------------------------|
| GET    | `/api/v1/stores/`               | List stores (filterable) |
| GET    | `/api/v1/stores/{id}/`          | Store detail             |
| POST   | `/api/v1/stores/`               | Create store (owner)     |
| PUT    | `/api/v1/stores/{id}/`          | Update store (owner)     |
| GET    | `/api/v1/stores/nearby/`        | Nearby stores (geo)      |

### Products

| Method | Endpoint                           | Description                |
|--------|------------------------------------|----------------------------|
| GET    | `/api/v1/products/`                | List products (filterable) |
| GET    | `/api/v1/products/{id}/`           | Product detail             |
| POST   | `/api/v1/products/`                | Create product (owner)     |
| PUT    | `/api/v1/products/{id}/`           | Update product (owner)     |
| DELETE | `/api/v1/products/{id}/`           | Delete product (owner)     |
| GET    | `/api/v1/products/categories/`     | List categories            |

### Orders

| Method | Endpoint                              | Description                 |
|--------|---------------------------------------|-----------------------------|
| GET    | `/api/v1/orders/`                     | List user orders            |
| POST   | `/api/v1/orders/`                     | Create new order            |
| GET    | `/api/v1/orders/{id}/`                | Order detail                |
| POST   | `/api/v1/orders/{id}/cancel/`         | Cancel order                |
| POST   | `/api/v1/orders/{id}/accept/`         | Accept order (store owner)  |
| POST   | `/api/v1/orders/{id}/update-status/`  | Update status (driver)      |

### Delivery

| Method | Endpoint                              | Description                 |
|--------|---------------------------------------|-----------------------------|
| GET    | `/api/v1/delivery/active/`            | Get active delivery (driver)|
| POST   | `/api/v1/delivery/accept/{id}/`       | Accept delivery assignment  |
| POST   | `/api/v1/delivery/location/`          | Update driver location      |
| GET    | `/api/v1/delivery/zones/`             | List delivery zones         |

### Payments

| Method | Endpoint                              | Description                 |
|--------|---------------------------------------|-----------------------------|
| POST   | `/api/v1/payments/create-intent/`     | Create payment intent       |
| POST   | `/api/v1/payments/confirm/`           | Confirm payment             |
| GET    | `/api/v1/payments/history/`           | Payment history             |
| POST   | `/api/v1/payments/webhook/`           | Payment provider webhook    |

### WebSocket Endpoints

| Endpoint                            | Description                          |
|-------------------------------------|--------------------------------------|
| `ws://host/ws/orders/{order_id}/`   | Real-time order status updates       |
| `ws://host/ws/delivery/{order_id}/` | Live driver location for an order    |
| `ws://host/ws/driver/`              | Driver assignment notifications      |

---

## Roadmap

### Phase 1 - MVP (Current)
- [x] User authentication and role-based access
- [x] Store and product management
- [x] Shopping cart and order placement
- [x] Basic order lifecycle management
- [x] Real-time order tracking via WebSocket
- [x] Live delivery map with driver location
- [x] Docker containerization

### Phase 2 - Enhanced Experience
- [ ] Push notifications (FCM/APNs)
- [ ] Advanced search with Elasticsearch
- [ ] Product recommendations engine
- [ ] Customer loyalty/rewards program
- [ ] Multi-language support (i18n)
- [ ] Dark mode support

### Phase 3 - Scale and Optimize
- [ ] Horizontal scaling with Kubernetes
- [ ] CDN integration for static assets and images
- [ ] Database read replicas
- [ ] Rate limiting and API throttling per tier
- [ ] A/B testing framework
- [ ] Machine learning for demand forecasting

### Phase 4 - Business Expansion
- [ ] Subscription-based delivery pass
- [ ] Store advertising and promoted listings
- [ ] Multi-vendor marketplace features
- [ ] Recipe integration (auto-add ingredients to cart)
- [ ] Scheduled and recurring orders
- [ ] In-app chat between customer and driver

---

## Improvements

### Performance
- Implement database query optimization with `select_related` and `prefetch_related` across all querysets
- Add Redis caching for frequently accessed data (store listings, product catalogs)
- Implement database connection pooling with PgBouncer
- Use Celery for all email sending and heavy computations
- Optimize image delivery with WebP format and lazy loading

### Security
- Add rate limiting on authentication endpoints
- Implement CORS whitelisting for production
- Add request signing for webhook endpoints
- Enable Content Security Policy headers
- Implement audit logging for sensitive operations
- Add two-factor authentication support

### Reliability
- Add comprehensive test suites (unit, integration, e2e)
- Implement circuit breaker pattern for external service calls
- Add health check endpoints for all services
- Implement graceful degradation for non-critical features
- Add structured logging with correlation IDs
- Set up error tracking with Sentry

### Developer Experience
- Add OpenAPI/Swagger documentation generation
- Implement database seeding scripts for development
- Add pre-commit hooks for linting and formatting
- Create GitHub Actions CI/CD pipeline
- Add comprehensive API integration tests with pytest

---

## License

This project is licensed under the MIT License. See the LICENSE file for details.
