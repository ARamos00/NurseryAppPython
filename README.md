---

# Nursery Tracker — Django/DRF + React/TypeScript (Vite)

Production-grade **Django 5.2 + DRF 3.16** API with a lightweight **React + TypeScript (Vite)** frontend.

Track **taxa**, **plant materials**, **propagation batches**, **plants**, and **events** with:
**per-user tenancy**, **session auth + CSRF**, **OpenAPI docs**, **throttling**, **idempotency**,
**optimistic concurrency (ETag/If-Match)**, **bulk ops**, **CSV import/export**, **reports**,
**QR labels + public pages**, **auditing**, and **outbound webhooks**.

> The frontend consumes the frozen API mirror at **`/api/v1/`** to insulate UI changes from backend evolution.

---

## Table of Contents

* [Highlights](#highlights)
* [Architecture](#architecture)
* [Project Layout](#project-layout)
* [Getting Started](#getting-started)
* [Configuration (Backend)](#configuration-backend)
* [Frontend](#frontend)
* [API & Docs](#api--docs)
* [Domain Model](#domain-model)
* [Key Endpoints](#key-endpoints)
* [Data Operations](#data-operations)
* [Idempotency & Concurrency](#idempotency--concurrency)
* [Auditing & Webhooks](#auditing--webhooks)
* [Health, Throttling, Observability](#health-throttling-observability)
* [Testing](#testing)
* [Developer Seed & Reset](#developer-seed--reset)
* [Troubleshooting](#troubleshooting)
* [Versioning](#versioning)
* [License](#license)

---

## Highlights

* **Per-user tenancy** via owner-scoped querysets and `IsOwner` permissions.
* **SessionAuth + CSRF** (browser-friendly; CSRF required on unsafe methods).
* **OpenAPI 3** (Swagger UI + Redoc) with headers for idempotency/concurrency.
* **Idempotency**: `Idempotency-Key` for safe POST retries.
* **Optimistic concurrency**: ETag on GET; `If-Match` on write (412 on stale).
* **Labels & public pages**: rotatable tokens, QR SVG, visit analytics.
* **Bulk ops**: plant bulk status; batch harvest/cull/complete/archive.
* **CSV import/export** and **reports** (inventory/production).
* **Auditing** with diffs; **outbound webhooks** (queue + worker).
* **Material UI v7** frontend shell (unified theme, AppBar, standardized auth forms).

---

## Architecture

```
Browser (React/Vite)
   └── SessionAuth + CSRF
        └── DRF ViewSets & actions
             ├── Serializers (validation)
             ├── Owner-scoped QuerySets (tenancy)
             ├── ETag / If-Match (concurrency)
             ├── Idempotency cache (POST)
             ├── Signals (labels, auditing, webhooks)
             └── CSV/Reports/Imports/Exports
```

---

## Project Layout

```
NurseryApp/
├─ accounts/                         # Custom User model
├─ core/
│  ├─ models.py                      # OwnedModel / OwnedQuerySet
│  ├─ permissions.py                 # IsOwner
│  ├─ throttling.py                  # global + named scopes
│  ├─ middleware.py                  # Request-ID logging
│  └─ utils/                         # idempotency, concurrency, webhooks
├─ nursery/
│  ├─ models.py                      # Taxon, Material, Batch, Plant, Event, Label, Audit, Webhook*
│  ├─ api/                           # viewsets + actions (labels, imports, reports, bulk ops, v1 mirror)
│  ├─ public_views.py                # /p/<token>/ + /p/<token>/qr.svg
│  ├─ renderers.py                   # CSV
│  ├─ schema.py                      # OpenAPI extensions
│  └─ management/commands/           # dev_seed, deliver_webhooks, cleanup_idempotency
├─ nursery_tracker/
│  ├─ settings/{base,dev,prod}.py    # 12-factor split
│  └─ urls.py                        # routers, docs, public, health
└─ frontend/                         # React + TS (Vite)
   └─ src/
      ├─ api/                        # http.ts, auth.ts (+ tests)
      ├─ auth/                       # AuthContext, RequireAuth, LogoutButton
      ├─ components/                 # NavBar (MUI AppBar)
      ├─ pages/                      # Login, Register, Forgot/Reset, PasswordChange, Home
      ├─ theme/                      # muiTheme.ts, fonts.css
      └─ App.tsx, main.tsx
```

---

## Getting Started

**Prereqs**

* Python **3.12+**
* Node.js **18+**
* SQLite (dev) or PostgreSQL 14+ (prod recommended)

**Backend**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

**Frontend**

```bash
cd frontend
npm ci
npm run dev    # http://localhost:5173 (5174 if busy)
```

> If you proxy `/api` in Vite, keep ports aligned with CSRF trusted origins (see below).

---

## Configuration (Backend)

| Variable                  | Purpose                        | Typical Dev                                   |
| ------------------------- | ------------------------------ | --------------------------------------------- |
| `DEBUG`                   | Enable debug                   | `True`                                        |
| `SECRET_KEY`              | Django secret                  | `dev-change-me`                               |
| `DATABASE_URL`            | DB connection                  | `sqlite:///db.sqlite3`                        |
| `ALLOWED_HOSTS`           | Host allowlist                 | `127.0.0.1,localhost`                         |
| `CSRF_TRUSTED_ORIGINS`    | Origin allowlist for CSRF      | include backend (8000) + frontend (5173/5174) |
| `CSRF_COOKIE_HTTPONLY`    | SPA needs to read cookie       | `False` in dev                                |
| `CSRF_COOKIE_SAMESITE`    | Cookie SameSite                | `Lax`                                         |
| `SESSION_COOKIE_SAMESITE` | Cookie SameSite                | `Lax`                                         |
| `ENFORCE_IF_MATCH`        | Require `If-Match` on write    | `False` dev; `True` prod                      |
| `ENABLE_REGISTRATION`     | Toggle `/auth/register/`       | `True` dev; `False` prod                      |
| `MAX_REQUEST_BYTES`       | Request size cap               | optional                                      |
| `MAX_IMPORT_BYTES`        | CSV upload cap (bytes)         | e.g. `5000000`                                |
| `IMPORT_MAX_ROWS`         | Max rows per import            | e.g. `50000`                                  |
| `EXPORT_MAX_ROWS`         | Row cap for exports            | optional                                      |
| `WEBHOOKS_*`              | HTTPS/signature/backoff/limits | see settings                                  |

---

## Frontend

* **Auth shell** using `AuthContext` + `RequireAuth`.
* **API client** targets **`/api/v1/`**, always `credentials: 'include'`.
* **CSRF**: GET primes cookie; unsafe methods send `X-CSRFToken`.
* **UI**: **Material UI v7** theme + AppBar; auth pages standardized.

**Vite dev proxy (example)**

```ts
// vite.config.ts
server: {
  port: 5173,
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
      cookieDomainRewrite: '',
    },
  },
}
```

---

## API & Docs

* **API root**: `http://127.0.0.1:8000/api/`
* **v1 mirror**: `http://127.0.0.1:8000/api/v1/`
* **OpenAPI schema**: `/api/schema/`
* **Swagger UI**: `/api/docs/`
* **Redoc**: `/api/redoc/`
* **Admin**: `/admin/`
* **Health**: `/health/`
* **Public label page**: `/p/<RAW_TOKEN>/`

---

## Domain Model

* **Taxon** → unique per user by *(scientific\_name, cultivar?, clone\_code?)*
* **PlantMaterial** (FK→Taxon) → type, lot, provenance
* **PropagationBatch** (FK→PlantMaterial) → method, status, quantities, started\_on
* **Plant** (FK→Taxon; optional FK→Batch) → status, quantity, acquired\_on (soft-deletable)
* **Event** → targets exactly one of `{batch | plant}`
* **Label / LabelToken / LabelVisit** → QR flows + analytics (tokens stored as hash+prefix)
* **AuditLog** → immutable changes
* **WebhookEndpoint / WebhookDelivery** → outbound events

**Relationships (simplified)**

```
Taxon 1─* PlantMaterial 1─* PropagationBatch 1─* Plant
Event → exactly one of {PropagationBatch | Plant}
Label → GFK to {Plant, PropagationBatch, PlantMaterial}
```

---

## Key Endpoints

Owner-scoped CRUD (filter/search/order/paginate):

* `GET/POST /api/taxa/`
* `GET/POST /api/materials/`
* `GET/POST /api/batches/`
* `GET/POST /api/plants/`
* `GET/POST /api/events/`

**Archive (soft delete)**

* `POST /api/plants/{id}/archive/`
* `POST /api/batches/{id}/archive/`

**Labels & Public Pages**

* `POST /api/labels/` → returns `{ token (once), public_url, ... }`
* `POST /api/labels/{id}/rotate/` → new raw token (old revoked)
* `POST /api/labels/{id}/revoke/`
* `GET /api/labels/{id}/qr/?token=<RAW>` → owner QR (no-store)
* `GET /p/<RAW>/` → public page (records visit)
* `GET /p/<RAW>/qr.svg` → public QR (immutable cache)
* `GET /api/labels/{id}/stats/?days=N` → visits summary/series

---

## Data Operations

**Bulk ops**

* Plants: `POST /api/plants/bulk/status/` → updates + per-plant `Event`
* Batches: `POST /api/batches/{id}/harvest|cull|complete|archive/`

**Imports (CSV multipart; throttled)**

* `/api/imports/taxa/` → `scientific_name,cultivar,clone_code`
* `/api/imports/materials/` → `taxon_id,material_type,lot_code,notes`
* `/api/imports/plants/?dry_run=1` → `taxon_id,batch_id?,status?,quantity?,acquired_on?,notes?`

**Exports**

* `/api/events/export/?format=csv|json`

  * CSV header: `id,happened_at,event_type,target_type,batch_id,plant_id,quantity_delta,notes`
  * Uses `X-Export-Total/Limit/Truncated` when capped

**Reports (throttled)**

* Inventory: `/api/reports/inventory/?format=json|csv`
* Production: `/api/reports/production/?from=YYYY-MM-DD&to=YYYY-MM-DD&format=json|csv&group_by=day?`

---

## Idempotency & Concurrency

**Idempotency (POST)**

```
Idempotency-Key: <client-stable-key>
```

First success for `(user, method, path, body-hash)` is cached and replayed on duplicates.

**Optimistic Concurrency**

* GET detail returns `ETag`.
* PUT/PATCH/DELETE require `If-Match: <etag>` when `ENFORCE_IF_MATCH=True`.
* Stale writes → **412 Precondition Failed**.

---

## Auditing & Webhooks

* **Audit logs**: `GET /api/audit/` (filters by model/action/date). Soft-deletes recorded as `delete`.
* **Webhooks**: per-user endpoints, HMAC/signature, queued deliveries.

  * Worker: `python manage.py deliver_webhooks`

---

## Health, Throttling, Observability

* **Health**: `/health/` (200 or 503 with DB check)
* **Throttling**: global (`user`, `anon`) + named scopes (`wizard-seed`, `events-export`, `label-public`, `imports`, `reports-read`, `audit-read`, `labels-read`)
* **Observability**: Request-ID middleware adds `X-Request-ID` and logs one structured line per request.

---

## Testing

**Backend**

```bash
python manage.py check
python manage.py test -v 2
```

**Frontend**

```bash
cd frontend
npm test        # vitest
npm run typecheck
```

---

## Developer Seed & Reset

```bash
rm -f db.sqlite3
python manage.py migrate
python manage.py dev_seed --reset --size=MEDIUM
```

Creates an idempotent, linked dataset for exploration.

---

## Troubleshooting

* **403 CSRF on login/logout/register**
  Ensure `X-CSRFToken` is sent; `CSRF_COOKIE_HTTPONLY=False` in dev; add current frontend origin (5173/5174) to `CSRF_TRUSTED_ORIGINS`.

* **401/403 on `/auth/me/`**
  Not logged in / expired session. `RequireAuth` redirects to `/login?next=...`.

* **412 Precondition Failed**
  ETag mismatch → GET fresh resource, retry with `If-Match`.

* **429 Too Many Requests**
  Throttle exceeded → back off; see names/rates in settings.

* **413 Request Too Large**
  Increase `MAX_IMPORT_BYTES` or split file.

* **Vite port drift**
  Lock with `strictPort: true` or update `CSRF_TRUSTED_ORIGINS`.

---

## Versioning

* Primary surface: **`/api/`**
* Frozen mirror: **`/api/v1/`** (frontend uses this)

---
