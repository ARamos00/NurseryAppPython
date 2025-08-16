# Nursery Tracker — Backend-First Django/DRF

A clean, production-grade **Django 5.2 + Django REST Framework 3.16** backend for tracking nursery data (taxa, plant materials, propagation batches, plants, and events). Built **backend-first** with strict per-user tenancy, session auth + CSRF, OpenAPI docs, throttling, health checks, idempotency, optimistic concurrency (ETag/If-Match), bulk ops, imports/exports, reports, QR labels + public pages, and outbound webhooks.

> **Status**: Backend API is the product surface. A separate UI can be layered later without changing API contracts.

---

## Contents

- [Highlights](#highlights)
- [Architecture](#architecture)
- [Project Layout](#project-layout)
- [Getting Started](#getting-started)
- [Configuration (.env)](#configuration-env)
- [Run & Operate](#run--operate)
- [API Docs & Useful URLs](#api-docs--useful-urls)
- [Security & Tenancy](#security--tenancy)
- [Domain Model](#domain-model)
- [Core API Endpoints](#core-api-endpoints)
- [Seed Wizard (Phase 1)](#seed-wizard-phase1)
- [Labels, QR & Public Pages (Phase 2a)](#labels-qr--public-pages-phase2a)
- [Bulk Ops & Harvest Semantics (Phase 2b)](#bulk-ops--harvest-semantics-phase2b)
- [Exports](#exports)
- [Imports](#imports)
- [Reports](#reports)
- [Idempotency](#idempotency)
- [Optimistic Concurrency (ETag/If-Match)](#optimistic-concurrency-etagif-match)
- [Webhooks (outbound)](#webhooks-outbound)
- [Health, Throttling, Observability](#health-throttling-observability)
- [Testing](#testing)
- [Resetting Data / Re-seeding](#resetting-data--re-seeding)
- [Contributing & Extensibility](#contributing--extensibility)
- [Troubleshooting](#troubleshooting)

---

## Highlights

- **Per-user tenancy**: All data is owned; queries and object access are user-scoped.
- **Auth & CSRF**: SessionAuthentication with CSRF for unsafe methods.
- **OpenAPI 3**: Swagger UI + Redoc via drf-spectacular; Enum naming stabilized.
- **Modular API**: `nursery/api/` packages (viewsets, seed wizard, labels, bulk ops, exports, imports, reports).
- **Seed Wizard**: Guided creation of Taxon → Material (Seed) → Batch (Seed Sowing) → initial SOW event.
- **Labels & Public Pages**: Per-item labels with rotatable tokens, QR-friendly public pages, visit tracking.
- **Bulk Ops**: Plant status bulk updates (with events), batch harvest/cull helpers.
- **Exports/Imports**: CSV/JSON exports (events, inventory/production). CSV imports for taxa/materials/plants with dry-run and validations.
- **Reports**: Inventory snapshot + production summary/time-series with CSV or JSON.
- **Idempotency**: `Idempotency-Key` header for safe retries on key mutating endpoints.
- **Concurrency**: ETag on GET; If-Match required on write to prevent lost updates.
- **Webhooks**: Enqueue + deliver worker; signals emit events (feature-flag friendly).

---

## Architecture

accounts/ (custom User)
core/
models.py # OwnedModel, OwnedQuerySet
permissions.py # IsOwner object-level guard
throttling.py # (scoped) throttle helpers
utils/
idempotency.py # @idempotent decorator (header-based)
concurrency.py # ETag helpers (If-Match enforcement)
webhooks.py # enqueue() + delivery primitives
nursery/
models.py # Taxon, PlantMaterial, PropagationBatch, Plant, Event, Label, LabelToken, LabelVisit, AuditLog
serializers.py # Model serializers + Label target field + DTOs
api/
viewsets.py # CRUD ViewSets for core models
wizard_seed.py # Seed wizard ViewSet (multi-step + compose)
labels.py # LabelViewSet (create/rotate/revoke)
batch_ops.py # Batch actions (harvest, cull, complete)
plant_ops.py # Plant bulk status updates (sell/discard/etc.)
events_export.py # Event export action
imports.py # CSV import endpoints
reports.py # Inventory & production report endpoints
public_views.py # Public label page (token-based HTML)
renderers.py # PassthroughCSVRenderer (content negotiation)
schema.py # Enum name overrides for OpenAPI
signals.py # Label cleanup, plant terminal-state handling, webhooks
management/commands/
dev_seed.py # Idempotent developer seed
deliver_webhooks.py# Worker for outbound webhooks
templates/
public/label_detail.html # Human-friendly public page for labels
nursery_tracker/
settings/base.py, dev.py, prod.py
urls.py # Routers, docs, health, public page

pgsql
Copy
Edit

**Tenancy**: All domain models subclass `core.OwnedModel` (fields: `user`, `created_at`, `updated_at`). ViewSets filter by `request.user`. `IsOwner` enforces object access.

---

## Project Layout

```text
NurseryApp/
├─ accounts/
├─ core/
│  ├─ models.py
│  ├─ permissions.py
│  ├─ throttling.py
│  └─ utils/
│     ├─ idempotency.py
│     ├─ concurrency.py
│     └─ webhooks.py
├─ nursery/
│  ├─ api/
│  │  ├─ __init__.py
│  │  ├─ viewsets.py
│  │  ├─ wizard_seed.py
│  │  ├─ labels.py
│  │  ├─ batch_ops.py
│  │  ├─ plant_ops.py
│  │  ├─ events_export.py
│  │  ├─ imports.py
│  │  └─ reports.py
│  ├─ management/commands/
│  │  ├─ dev_seed.py
│  │  └─ deliver_webhooks.py
│  ├─ templates/public/label_detail.html
│  ├─ public_views.py
│  ├─ renderers.py
│  ├─ schema.py
│  ├─ serializers.py
│  ├─ signals.py
│  ├─ models.py
│  └─ tests/  (extensive suite)
├─ nursery_tracker/
│  ├─ settings/
│  │  ├─ base.py
│  │  ├─ dev.py
│  │  └─ prod.py
│  └─ urls.py
└─ README.md
Getting Started
Prereqs
Python 3.12+

Optional: PostgreSQL 14+ (dev defaults to SQLite; production recommends Postgres)

Setup (Windows PowerShell)
powershell
Copy
Edit
py -m venv venv
venv\Scripts\activate
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
copy .env.example .env  # or create manually; see below
Setup (macOS/Linux)
bash
Copy
Edit
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env  # optional
Configuration (.env)
Minimum:

ini
Copy
Edit
DEBUG=True
SECRET_KEY=dev-insecure-change-me
# Dev DB: SQLite
DATABASE_URL=sqlite:///db.sqlite3

ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

# Throttling (defaults shown; can be tuned per env)
DRF_THROTTLE_RATE_USER=200/min
DRF_THROTTLE_RATE_ANON=50/min
DRF_THROTTLE_RATE_WIZARD_SEED=30/min
DRF_THROTTLE_RATE_EVENTS_EXPORT=10/min
DRF_THROTTLE_RATE_LABEL_PUBLIC=120/min
# If you expose a "test" action for webhook admin later:
DRF_THROTTLE_RATE_WEBHOOKS_ADMIN=30/min
Production deltas (see settings/prod.py):

ini
Copy
Edit
DJANGO_SETTINGS_MODULE=nursery_tracker.settings.prod
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=15552000
DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/DB
Run & Operate
bash
Copy
Edit
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
# In a second terminal (if using webhooks):
python manage.py deliver_webhooks
Dev seed (idempotent):

bash
Copy
Edit
python manage.py dev_seed --reset --size=MEDIUM
# users: alice / bob  (password: pass12345)
API Docs & Useful URLs
Admin: http://127.0.0.1:8000/admin/

API root: http://127.0.0.1:8000/api/

Swagger UI: http://127.0.0.1:8000/api/docs/

Redoc: http://127.0.0.1:8000/api/redoc/

OpenAPI JSON: http://127.0.0.1:8000/api/schema/

Health: http://127.0.0.1:8000/health/

Public label page: http://127.0.0.1:8000/p/<token>/

Security & Tenancy
Auth: SessionAuthentication; login via admin or browsable API.

CSRF: Required for unsafe methods (POST/PUT/PATCH/DELETE). Fetch CSRF cookie via any GET first; send as X-CSRFToken.

Tenancy: All domain queries and object access are per-user (OwnedModel, IsOwner).

Public QR pages: Token-based; tokens are rotatable; revocation is immediate. Public page shows a minimal, non-sensitive subset.

Domain Model
Taxon — scientific_name, optional cultivar, clone_code. Unique per user across (scientific_name, cultivar, clone_code).

PlantMaterial — FK → Taxon; material_type (Seed/Cutting/...); optional lot_code (conditionally unique per user when set).

PropagationBatch — FK → PlantMaterial; method, status, started_on, quantity_started.

Plant — FK → Taxon; optional FK → PropagationBatch; status, quantity, acquired_on.

Event — Action for either a batch or a plant (XOR constraint); event_type, happened_at, optional quantity_delta, notes.

Label — Generic to Plant|PropagationBatch|PlantMaterial; points to an optional active_token.

LabelToken — Hash + prefix; revocable; raw tokens are never stored.

LabelVisit — Public page view analytics (coarse request metadata).

AuditLog — Lightweight audit trail for mutations (actor, changes, request metadata).

Indexes & constraints are in nursery/models.py and tuned for common queries.

Core API Endpoints
CRUD ViewSets (owner-scoped):

/api/taxa/

/api/materials/

/api/batches/

/api/plants/

/api/events/

Filtering, search, ordering, pagination are enabled; see Swagger for per-resource fields.

Seed Wizard (Phase 1)
Wizard path: /api/wizard/seed/… (scoped, throttled by wizard-seed).

POST /api/wizard/seed/select-taxon/

Body: { "taxon_id": 1 } or { "taxon": { ...Taxon fields... } }

200/201 → { "taxon_id": 1, "next": { "material": "/api/wizard/seed/create-material/" } }

POST /api/wizard/seed/create-material/

Body: { "taxon_id": 1, "material": { "material_type": "SEED", "lot_code": "LOT-001", ... } }

201 → { "material_id": 2, "next": { "batch": "/api/wizard/seed/create-batch/" } }

POST /api/wizard/seed/create-batch/

Body: { "material_id": 2, "batch": { "method": "SEED_SOWING", "quantity_started": 24, "started_on": "YYYY-MM-DD" } }

201 → { "batch_id": 3, "next": { "sow": "/api/wizard/seed/log-sow/" } }

POST /api/wizard/seed/log-sow/

Body: { "batch_id": 3, "event": { "notes": "Started tray A" } } (defaults to event_type=SOW)

201 → { "event_id": 4, "complete": true, "links": { "batch": "/api/batches/3/" } }

One-shot compose:

POST /api/wizard/seed/compose/ with { taxon?, material, batch, event? } — creates the chain atomically.

All wizard endpoints accept optional Idempotency-Key.

Labels, QR & Public Pages (Phase 2a)
Label CRUD: /api/labels/
Public page (no auth): /p/<token>/

POST /api/labels/ — Create new label (or rotate on ?force=true) for a target:

json
Copy
Edit
{ "target": { "type": "plant"|"batch"|"material", "id": 123 } }
Returns once: token and public_url. The token is not stored; only a hash and prefix are.

POST /api/labels/{id}/rotate/ — Revokes the previous token and returns a new raw token once.

POST /api/labels/{id}/revoke/ — Revokes active token; safe to call repeatedly.

Public page /p/<token>/ — Human-friendly HTML: classification, method, started/acquired dates, basic counts; records a LabelVisit. Revoked/unknown tokens return 404.

Terminal status behavior: If a Plant is set to SOLD|DEAD|DISCARDED, any active label is automatically revoked.

Bulk Ops & Harvest Semantics (Phase 2b)
POST /api/plants/bulk/status/

json
Copy
Edit
{ "ids": [1,2,3], "status": "SOLD", "notes": "Sold at market" }
Updates statuses; emits corresponding Event rows (e.g., SELL).

Batch helpers (per-resource actions):

POST /api/batches/{id}/harvest/ — Reduces available quantity via negative quantity_delta event; can optionally create new Plant rows (out-planting).

POST /api/batches/{id}/cull/ — Loss/waste (negative delta).

POST /api/batches/{id}/complete/ — Set status and finalize.

Harvest semantics are row-based: Plants may leave a batch over time; batch available_quantity() = quantity_started + sum(events.quantity_delta) (harvest/cull write negatives).

Exports
Events
GET /api/events/export/?format=csv|json
CSV columns:

bash
Copy
Edit
id,happened_at,event_type,target_type,batch_id,plant_id,quantity_delta,notes
target_type ∈ batch|plant

CSV returns text/csv; JSON returns a plain list (not paginated).

Reports (also support CSV)
See Reports below.

Imports
CSV multipart endpoints:

POST /api/imports/taxa/ — CSV with headers:

Copy
Edit
scientific_name,cultivar,clone_code
Idempotent on exact row content (use Idempotency-Key for full-file replay protection).

POST /api/imports/materials/ — Headers:

Copy
Edit
taxon_scientific_name,material_type,lot_code,notes
Validates material_type choice; taxon_scientific_name must resolve to an owned Taxon.

POST /api/imports/plants/?dry_run=1|0 — Headers:

lua
Copy
Edit
scientific_name,batch_id,quantity,acquired_on,notes,status
dry_run=1 performs validation only; returns counts and first N errors.

status must be a valid PlantStatus (e.g., ACTIVE).

Validation & errors follow DRF’s standard shape:

json
Copy
Edit
{ "detail": "...", "row": 12, "errors": { "field": ["message"] } }
Reports
Endpoints under /api/reports/:

Inventory: GET /api/reports/inventory/?format=csv|json

Snapshot by taxon, status, and counts (batches/plants).

CSV is convenient for spreadsheets; JSON suitable for charts.

Production: GET /api/reports/production/?granularity=day|week|month&format=csv|json

Aggregates starts, germinations, pot-ups, sales, discards over time.

Both endpoints are owner-scoped, support common date filters, and stream CSV using a minimal CSV renderer for content negotiation.

Idempotency
For endpoints marked idempotent (e.g., wizard steps, label create/rotate, imports), send an Idempotency-Key header:

pgsql
Copy
Edit
Idempotency-Key: <client-generated-uuid-or-stable-key>
The server stores the first successful response for the tuple (user, method, path, body-hash) for a retention window and replays it for subsequent identical requests.

Optimistic Concurrency (ETag/If-Match)
Read: GET detail endpoints include an ETag header (weak tag, includes model name, pk, and timestamp/version).

Write: PUT/PATCH/DELETE must supply If-Match: <etag> retrieved from the last GET.

If the ETag is stale (object changed), server returns 412 Precondition Failed.

Tests cover: “retrieve → update with If-Match (200)” and “stale If-Match (412)”.

Webhooks (outbound)
Emitted by model signals (e.g., creation/updates) when enabled.

Enqueue via core.utils.webhooks.enqueue_for_user(...).

Deliveries are sent by the worker:

bash
Copy
Edit
python manage.py deliver_webhooks
Delivery metadata and statuses are recorded per user.

Headers include event metadata and a signature (see implementation). Payload is JSON.

Retries and backoff are handled in the worker (see command code).
Note: Admin CRUD for webhook endpoints can be added later; current implementation is signal-driven and worker-delivered.

Health, Throttling, Observability
Health: /health/ returns 200 with DB “ok”, or 503 if DB down (tests cover both).

Throttling:

UserRateThrottle (default 200/min), AnonRateThrottle (50/min).

Scoped throttles:

wizard-seed (default 30/min)

events-export (10/min)

label-public (120/min)

Tune via env: DRF_THROTTLE_RATE_<SCOPE>=X/min.

OpenAPI polish: Enum naming collisions resolved via SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"].

Testing
Run all tests:

bash
Copy
Edit
python manage.py test
Coverage includes:

Models: Constraints (Taxon uniqueness per user, Event XOR), OwnedQuerySet.for_user.

API: Auth required; ownership isolation; create auto-sets user.

Filters: Filtering/search/ordering/pagination determinism.

Throttling: User/anon/scoped throttles (429 coverage).

Wizard: Stepwise + compose; idempotency.

Labels: Create/rotate/revoke; public page; analytics visit recording.

Bulk Ops: Plant bulk status → Event emissions; batch helpers.

Exports: Events CSV/JSON; content-type and headers.

Imports: Taxa/materials/plants with validations; dry-run.

Reports: Inventory + production (CSV/JSON).

Concurrency: ETag on GET; If-Match on write (412 on stale).

Webhooks: Enqueue + worker delivery path basics.

Resetting Data / Re-seeding
Because dev is flexible:

bash
Copy
Edit
# Option A: fresh SQLite file
rm -f db.sqlite3 && python manage.py migrate && python manage.py dev_seed --reset

# Option B: Postgres (example)
createdb nursery_db
export DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/nursery_db
python manage.py migrate
python manage.py dev_seed --reset --size=MEDIUM
If you ever drop migrations during early dev, recreate fresh initial ones:

bash
Copy
Edit
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
python manage.py makemigrations
python manage.py migrate
Contributing & Extensibility
New owned model: subclass core.OwnedModel; admin with owner scoping; CRUD ViewSet with user filtering + perform_create; add serializer, filters, tests.

Custom actions: prefer @action on ViewSets; annotate with extend_schema.

CSV endpoints: keep responses streaming and expose text/csv via PassthroughCSVRenderer.

Public views: implement as DRF APIView/GenericAPIView with AllowAny; throttle via a named scope.

Troubleshooting
403 (CSRF) on POST:

Get a CSRF cookie first (any GET).

Send session cookies + X-CSRFToken header.

404 on /api/events/export/ in tests:

Ensure the router registers the export action and the test client path matches the registered pattern. We ship a route that resolves to event-export and returns CSV/JSON based on ?format=.

OpenAPI enum warnings:

We set ENUM_NAME_OVERRIDES in settings/base.py. If you add new enums or fields named status, add overrides to keep the schema clean.

Label public page 404:

The token may be revoked or unknown. Rotate or create a new label to issue a fresh token.