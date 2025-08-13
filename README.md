Nursery Tracker — Backend-First Django/DRF
A clean, production-grade Django 5 + DRF backend for tracking nursery data (taxa, materials, propagation batches, plants, and events). Built backend-first, with per-user data ownership, session auth, CSRF, OpenAPI docs, health checks, throttling, and strong tests.

Tech Stack
Django 5.2.x

Django REST Framework 3.16.x

django-filter 25.x

drf-spectacular (OpenAPI 3)

psycopg (PostgreSQL driver)

django-environ (12-factor settings)

Python 3.12+ recommended

Project Structure
bash
Copy
Edit
nursery_tracker/
  settings/
    __init__.py
    base.py        # common settings
    dev.py         # local dev defaults
    prod.py        # hardened for deployment
  urls.py          # routers, docs, health, admin
  asgi.py / wsgi.py
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
Core Concepts
Custom User early: accounts.User (subclasses AbstractUser) to avoid migration pain later.

Per-user tenancy: All domain models inherit core.OwnedModel (user FK + audit fields) and use OwnedQuerySet.for_user(user) to scope queries.

API isolation: ViewSets filter by request.user and set user on create; object access enforced by core.permissions.IsOwner.

Session auth + CSRF: Browsable API/admin use Django sessions. No JWT yet; add later if you ship a SPA/mobile client.

Filtering/ordering/search: Enabled globally; each ViewSet declares its fields.

OpenAPI 3 docs: drf-spectacular with Swagger and Redoc.

Health endpoint: /health/ (no auth) with DB connectivity check.

Throttling: DRF user/anon throttles (env-tunable).

Settings split: base/dev/prod with django-environ.

Tests first: Coverage for models, ownership, CSRF, filters/ordering/pagination, throttling, and health.

Quickstart
1) Create venv & install
Windows (PowerShell):

powershell
Copy
Edit
py -m venv venv
venv\Scripts\activate
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
macOS/Linux:

bash
Copy
Edit
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
If you don’t have requirements.txt yet, freeze after installing:
pip freeze > requirements.txt

2) Settings & environment
Create a .env at the repo root:

ini
Copy
Edit
DEBUG=True
SECRET_KEY=dev-insecure-change-me
DATABASE_URL=sqlite:///db.sqlite3

ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

# Throttling (optional overrides)
DRF_THROTTLE_RATE_USER=200/min
DRF_THROTTLE_RATE_ANON=50/min
The project defaults to nursery_tracker.settings.dev for manage.py/ASGI/WSGI.

3) Migrate & run
powershell
Copy
Edit
py manage.py migrate
py manage.py createsuperuser
py manage.py runserver
Admin: http://127.0.0.1:8000/admin/

API root: http://127.0.0.1:8000/api/

Swagger: http://127.0.0.1:8000/api/docs/

Redoc: http://127.0.0.1:8000/api/redoc/

Schema (JSON): http://127.0.0.1:8000/api/schema/

Health: http://127.0.0.1:8000/health/

Root redirect: / → /api/docs/

Domain Model Overview
Taxon: scientific_name, optional cultivar, clone_code (unique per user).

PlantMaterial: link to Taxon, material_type (seed/cutting/…),
optional lot_code (unique per user when provided).

PropagationBatch: link to PlantMaterial, method, status, started_on, quantity_started.

Plant: link to Taxon and optional PropagationBatch, status, quantity, acquired_on.

Event: timestamped action for either a batch or a plant (XOR, validated at model/serializer).

All domain models include user, created_at, updated_at. Indexes and constraints are in place for correctness and performance.

API Design
Shape: DRF ModelViewSet + Router per model.

Auth: SessionAuthentication (login via admin or /api/ “Log in” in the browsable API).

Permissions: IsAuthenticated + IsOwner (object-level).

Query scoping: get_queryset() filters by request.user; perform_create() sets user.

Filtering: ?field=value per filterset_fields.

Search: ?search=term across search_fields.

Ordering: ?ordering=field or ?ordering=-field.

Pagination: Page-number pagination; default page size in REST_FRAMEWORK["PAGE_SIZE"].

Example queries:

sql
Copy
Edit
GET /api/batches/?status=STARTED&ordering=-started_on
GET /api/materials/?search=pendula
GET /api/plants/?taxon=3&status=ACTIVE
CSRF & Sessions (unsafe methods)
When using the browsable API or a client with session auth:

GET a page to receive a CSRF cookie (e.g., /admin/login/ or the list endpoint).

Send X-CSRFToken header with the cookie value on POST/PUT/PATCH/DELETE.

Include the session cookie.

Tests verify both the “403 without CSRF” and “201 with CSRF” flows.

OpenAPI Docs
Schema: /api/schema/ (OpenAPI 3 JSON)

Swagger UI: /api/docs/ (persists authorization)

Redoc: /api/redoc/

Edit SPECTACULAR_SETTINGS in settings/base.py for title/description/servers/contact.

Health & Observability
Health: /health/ returns { "app": "nursery-tracker", "db": "ok", "time": ... }

If DB connectivity fails, returns HTTP 503 with { "db": "down" }.

Prod logging: concise console logging for root, django.request, and django.security (tunable).

Throttling
Enabled globally:

AnonRateThrottle (default 50/min, env-tunable)

UserRateThrottle (default 200/min, env-tunable)

Environment variables:

ini
Copy
Edit
DRF_THROTTLE_RATE_USER=200/min
DRF_THROTTLE_RATE_ANON=50/min
Admin (Back Office)
Admin is owner-scoped for non-superusers (lists and FK choices limited to request.user).

user is auto-set on save when missing.

Test Suite
Run everything:

bash
Copy
Edit
python manage.py test
Highlights:

Models: uniqueness, OwnedQuerySet.for_user, Event XOR and ownership validation.

API: auth required, per-user isolation, CSRF behavior, create ownership.

Filters: filtering/search/ordering on all endpoints; deterministic pagination.

Throttling: 429s for user/anon via burst throttles (patched in tests).

Health: 200 OK (DB ok) and 503 (DB down via mock).

Dev Seed Data
Idempotent seed command to populate realistic data for alice and bob (passwords pass12345):

bash
Copy
Edit
python manage.py dev_seed              # SMALL
python manage.py dev_seed --reset
python manage.py dev_seed --reset --size=MEDIUM
python manage.py dev_seed --reset --size=LARGE
Data includes taxa, materials, batches, plants, and event timelines—visible in admin and via API.

Database
Dev default: SQLite (DATABASE_URL=sqlite:///db.sqlite3)

Production: PostgreSQL via psycopg 3.

Example URL: postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME

Deployment
Set environment variables (e.g., via .env.prod or your platform):

ini
Copy
Edit
DJANGO_SETTINGS_MODULE=nursery_tracker.settings.prod
SECRET_KEY=<strong secret>
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DB
ALLOWED_HOSTS=example.com,www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=15552000
DRF_THROTTLE_RATE_USER=200/min
DRF_THROTTLE_RATE_ANON=50/min
python manage.py migrate

python manage.py collectstatic --no-input

Run under ASGI (recommended) or WSGI behind HTTPS. If behind a proxy, ensure:

SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https")

Proxy forwards correct headers.

Verify python manage.py check --deploy is clean.

Extending the Backend
Add fields to User: extend accounts.User (we already use a custom user).

New owned models: subclass core.OwnedModel, register in admin via OwnerScopedAdmin, and follow the ViewSet pattern (scope by request.user, set user on create).

Range filters: switch filterset_fields to dict form (e.g., {"happened_at": ["gte","lte"]}) and add matching tests.

Token/JWT auth: add only when shipping a separate SPA/mobile client; keep sessions for admin/browsable API.

Troubleshooting
404 at /: By design; root redirects to /api/docs/. Change in urls.py if you want / → /api/.

Schema 500: Ensure REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"] = "drf_spectacular.openapi.AutoSchema".

CSRF 403: Ensure you sent the CSRF cookie and X-CSRFToken header with session cookie for unsafe methods.

Unique constraint errors: Model constraints are per-user; duplicates across users are allowed.