# Nursery Tracker — Backend-First Django/DRF

A clean, production-grade **Django 5 + Django REST Framework** backend for tracking nursery data (taxa, plant materials, propagation batches, plants, and events). Built **backend-first**, with strict per-user data ownership, session auth + CSRF, OpenAPI docs, health checks, throttling, and a solid test suite.

> **Status:** Backend API and admin are the primary interface. A separate UI can be layered later without changing core contracts.

---

## Table of Contents

* [Features](#features)
* [Tech Stack](#tech-stack)
* [Project Layout](#project-layout)
* [Getting Started](#getting-started)
* [API Docs & Useful URLs](#api-docs--useful-urls)
* [Security, Auth & CSRF](#security-auth--csrf)
* [Domain Model Overview](#domain-model-overview)
* [API Design & Querying](#api-design--querying)
* [Ownership & Permissions](#ownership--permissions)
* [Admin (Back Office)](#admin-back-office)
* [Health & Observability](#health--observability)
* [Throttling](#throttling)
* [Dev Seed Data](#dev-seed-data)
* [Testing](#testing)
* [Deployment](#deployment)
* [Extending the Backend](#extending-the-backend)
* [Troubleshooting](#troubleshooting)

---

## Features

* **Per-user tenancy**: All domain records are owned and server-side scoped.
* **Session auth + CSRF**: Safe by default for the browsable API and admin.
* **OpenAPI 3** via drf-spectacular: Swagger UI, Redoc, and JSON schema.
* **Filtering/Search/Ordering**: Globally enabled; per-viewset configuration.
* **Owner-scoped admin**: Non-superusers only see their own data.
* **Health checks**: `/health/` with DB connectivity status.
* **Throttling**: User/anon burst throttles, env-tunable.
* **Tests**: Models, permissions/ownership, CSRF behavior, filters, throttling, health.

---

## Tech Stack

* **Python**: 3.12+
* **Django**: 5.2.x
* **Django REST Framework**: 3.16.x
* **django-filter**: 25.x
* **drf-spectacular** (OpenAPI 3)
* **psycopg** (PostgreSQL driver)
* **django-environ** (12-factor settings)

---

## Project Layout

```
nursery_tracker/
  settings/
    __init__.py
    base.py        # common settings
    dev.py         # local dev defaults
    prod.py        # hardened for deployment
  urls.py          # routers, docs, health, admin
  asgi.py
  wsgi.py
accounts/
  models.py        # custom User (AbstractUser)
  admin.py
core/
  models.py        # OwnedModel + OwnedQuerySet
  permissions.py   # IsOwner (object-level)
  views.py         # /health/ endpoint
nursery/
  models.py        # Taxon, PlantMaterial, PropagationBatch, Plant, Event
  admin.py         # owner-scoped admin
  api.py           # ViewSets (per-user scoping)
  serializers.py
  management/commands/dev_seed.py
nursery/tests/
  test_models.py
  test_api.py
  test_api_filters.py
  test_throttling.py
```

---

## Getting Started

### 1) Create venv & install

**Windows (PowerShell)**

```powershell
py -m venv venv
venv\Scripts\activate
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

**macOS/Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `requirements.txt` doesn’t exist yet:

```bash
pip freeze > requirements.txt
```

### 2) Configure environment

Create a `.env` at the repo root:

```ini
DEBUG=True
SECRET_KEY=dev-insecure-change-me
DATABASE_URL=sqlite:///db.sqlite3

ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

# Throttling (optional overrides)
DRF_THROTTLE_RATE_USER=200/min
DRF_THROTTLE_RATE_ANON=50/min
```

> The project defaults to `nursery_tracker.settings.dev` for manage.py/ASGI/WSGI.

### 3) Initialize DB & run

```powershell
py manage.py migrate
py manage.py createsuperuser
py manage.py runserver
```

---

## API Docs & Useful URLs

* **Admin**: [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)
* **API root**: [http://127.0.0.1:8000/api/](http://127.0.0.1:8000/api/)
* **Swagger UI**: [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)
* **Redoc**: [http://127.0.0.1:8000/api/redoc/](http://127.0.0.1:8000/api/redoc/)
* **OpenAPI JSON**: [http://127.0.0.1:8000/api/schema/](http://127.0.0.1:8000/api/schema/)
* **Health**: [http://127.0.0.1:8000/health/](http://127.0.0.1:8000/health/)
* **Root redirect**: `/` → `/api/docs/`

---

## Security, Auth & CSRF

**Auth model**: SessionAuthentication for admin and the browsable API. No JWT by default.

**CSRF (unsafe methods)**:

1. **GET** any page first to receive a CSRF cookie (e.g., `/admin/login/` or a list endpoint).
2. Send the `X-CSRFToken` header with the cookie value on **POST/PUT/PATCH/DELETE**.
3. Include the session cookie.

**Quick curl example (local dev)**:

```bash
# 1) Prime cookies & CSRF by hitting a safe endpoint
curl -i -c cookies.txt http://127.0.0.1:8000/api/taxa/

# 2) Extract csrftoken from cookies.txt (or inspect Set-Cookie)
# 3) Send a POST with session cookie + CSRF header
curl -i -b cookies.txt -H "X-CSRFToken: <csrftoken>" \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8000/api/taxa/ \
  --data '{"scientific_name":"Acer palmatum","cultivar":"","clone_code":""}'
```

> Tests cover both: “403 without CSRF” and “201 with CSRF” flows.

---

## Domain Model Overview

* **Taxon**: `scientific_name`, optional `cultivar`, `clone_code` (unique **per user**).
* **PlantMaterial**: FK → Taxon; `material_type` (e.g., seed/cutting), optional `lot_code` (unique per user when provided).
* **PropagationBatch**: FK → PlantMaterial; `method`, `status`, `started_on`, `quantity_started`.
* **Plant**: FK → Taxon and optional FK → PropagationBatch; `status`, `quantity`, `acquired_on`.
* **Event**: timestamped action for either a **batch or a plant** (**XOR**, validated at model/serializer).

All domain models inherit `user`, `created_at`, `updated_at`. Indexes/constraints enforce correctness and performance.

---

## API Design & Querying

**Shape**: DRF `ModelViewSet` + router per model.
**Auth**: SessionAuthentication (login via admin or the browsable API’s “Log in”).
**Permissions**: `IsAuthenticated` + custom object-level `IsOwner`.
**Query scoping**: `get_queryset()` filters by `request.user`; `perform_create()` sets `user`.
**Filtering**: `?field=value` for fields declared in `filterset_fields`.
**Search**: `?search=term` across `search_fields`.
**Ordering**: `?ordering=field` (or `-field`).
**Pagination**: Page-number; default size from `REST_FRAMEWORK["PAGE_SIZE"]`.

**Examples**:

```text
GET /api/batches/?status=STARTED&ordering=-started_on
GET /api/materials/?search=pendula
GET /api/plants/?taxon=3&status=ACTIVE
```

---

## Ownership & Permissions

* **Custom user**: `accounts.User` (subclasses `AbstractUser`).
* **Per-user tenancy**: Domain models subclass `core.OwnedModel`.
* **Scoped querying**: `OwnedQuerySet.for_user(user)` and per-viewset filtering.
* **Object access**: Enforced by `core.permissions.IsOwner`.

---

## Admin (Back Office)

* Owner-scoped for non-superusers (lists and FK choices limited to `request.user`).
* `user` is auto-set on save when missing.

---

## Health & Observability

* `/health/` returns:

  ```json
  { "app": "nursery-tracker", "db": "ok", "time": "..." }
  ```

* If DB is unavailable: HTTP **503** with `{ "db": "down" }`.

* Production logging: concise console logging for `root`, `django.request`, and `django.security` (tunable).

---

## Throttling

Globally enabled:

* `AnonRateThrottle` (default **50/min**, env-tunable)
* `UserRateThrottle` (default **200/min**, env-tunable)

Environment overrides:

```ini
DRF_THROTTLE_RATE_USER=200/min
DRF_THROTTLE_RATE_ANON=50/min
```

---

## Dev Seed Data

Idempotent seed command populates realistic data for **alice** and **bob** (`pass12345`):

```bash
python manage.py dev_seed              # SMALL
python manage.py dev_seed --reset
python manage.py dev_seed --reset --size=MEDIUM
python manage.py dev_seed --reset --size=LARGE
```

Data covers taxa, materials, batches, plants, and event timelines (visible in admin and via API).

---

## Testing

Run the full suite:

```bash
python manage.py test
```

**What’s covered**:

* **Models**: Uniqueness, `OwnedQuerySet.for_user`, Event XOR & ownership validation.
* **API**: Auth required, per-user isolation, CSRF behavior, create ownership.
* **Filters**: Filtering/search/ordering on all endpoints; deterministic pagination.
* **Throttling**: 429s for user/anon (burst throttles patched in tests).
* **Health**: 200 OK (DB ok) and 503 (DB down via mock).

---

## Deployment

Environment (example):

```ini
DJANGO_SETTINGS_MODULE=nursery_tracker.settings.prod
SECRET_KEY=<strong secret>
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DB
ALLOWED_HOSTS=example.com,www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=15552000
DRF_THROTTLE_RATE_USER=200/min
DRF_THROTTLE_RATE_ANON=50/min
```

Commands:

```bash
python manage.py migrate
python manage.py collectstatic --no-input
```

Runtime:

* Prefer **ASGI** behind HTTPS; WSGI also supported.
* If behind a proxy, ensure:

  ```python
  SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
  ```

  and the proxy forwards correct headers.

Verify:

```bash
python manage.py check --deploy
```

**Database**:

* Dev default: `sqlite:///db.sqlite3`
* Production: PostgreSQL (`psycopg 3`)

  ```
  postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
  ```

---

## Extending the Backend

* **User fields**: Extend `accounts.User` (already a custom user).
* **New owned models**:

  1. Subclass `core.OwnedModel`.
  2. Register with `OwnerScopedAdmin`.
  3. Add a `ModelViewSet` (scope by `request.user`; set `user` on create).
  4. Wire up router + serializer + tests.
* **Range filters**: Switch `filterset_fields` to dict form (e.g., `{"happened_at": ["gte","lte"]}`) and add tests.
* **Token/JWT**: Add **only** when shipping a separate SPA/mobile client; keep sessions for admin/browsable API.

---

## Troubleshooting

* **404 at /**: By design; root redirects to `/api/docs/`. Change in `urls.py` if you prefer `/` → `/api/`.
* **Schema 500**: Ensure `REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"] = "drf_spectacular.openapi.AutoSchema"`.
* **CSRF 403**: Ensure you first received the CSRF cookie and then sent `X-CSRFToken` with the session cookie.
* **Unique constraint errors**: Constraints are **per user**; duplicates across users are allowed.
