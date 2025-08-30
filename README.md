````markdown
# Nursery Tracker — Django/DRF + React/TypeScript (Vite)

A production-grade **Django 5.2 + Django REST Framework 3.16** backend with a lightweight **React + TypeScript (Vite)** frontend shell.

Track **taxa**, **plant materials**, **propagation batches**, **plants**, **events** — with
**per-user tenancy**, **SessionAuth + CSRF**, **OpenAPI docs**, **throttling**, **idempotency**,
**optimistic concurrency (ETag/If-Match)**, **bulk ops**, **CSV imports/exports**, **reports**,
**QR labels + public pages**, **auditing**, and **outbound webhooks**.

> The API is the stable surface. The frontend consumes the frozen mirror at **`/api/v1/`** to insulate UI changes from backend evolution.

---

## Table of Contents

- [Highlights](#highlights)
- [Architecture Overview](#architecture-overview)
- [Project Layout](#project-layout)
- [Getting Started](#getting-started)
- [Configuration (Backend)](#configuration-backend)
- [Frontend (React + TypeScript + Vite)](#frontend-react--typescript--vite)
  - [Folder Layout](#folder-layout)
  - [Running the Frontend](#running-the-frontend)
  - [API Client Conventions](#api-client-conventions)
  - [Auth Flow (Pages & Components)](#auth-flow-pages--components)
  - [Testing (Frontend)](#testing-frontend)
  - [Common Frontend Pitfalls](#common-frontend-pitfalls)
- [API Docs & URLs](#api-docs--urls)
- [Security & Tenancy](#security--tenancy)
- [Domain Model](#domain-model)
- [Core API Endpoints](#core-api-endpoints)
- [Seed Wizard](#seed-wizard)
- [Labels, QR & Public Pages](#labels-qr--public-pages)
- [Bulk Operations](#bulk-operations)
- [Exports](#exports)
- [Imports](#imports)
- [Reports](#reports)
- [Idempotency](#idempotency)
- [Optimistic Concurrency](#optimistic-concurrency)
- [Audit Logs](#audit-logs)
- [Webhooks (Outbound)](#webhooks-outbound)
- [Health, Throttling, Observability](#health-throttling-observability)
- [Versioning](#versioning)
- [Testing (Backend)](#testing-backend)
- [Developer Seed & Reset](#developer-seed--reset)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Highlights

- **Per-user tenancy** — All domain models subclass an owned base and are scoped by `request.user`.
- **Session auth + CSRF** — Browser-friendly, production-safe defaults. CSRF is **required for unsafe methods**.
- **OpenAPI 3** — drf-spectacular (Swagger UI & Redoc). Custom components document idempotency/concurrency headers.
- **Idempotency** — Safe retries for POST using `Idempotency-Key`; first success is replayed.
- **Optimistic concurrency** — ETag on GET; `If-Match` required on write when enabled; 412 on stale.
- **Labels & public pages** — Rotatable/revocable tokens, owner/public QR SVG endpoints, visit analytics.
- **Bulk ops** — Plant bulk status; batch harvest/cull/complete; archive (soft delete) for plants/batches.
- **CSV imports/exports** — Events export (CSV/JSON). CSV imports for taxa/materials/plants with dry-run.
- **Reports** — Inventory snapshot and production summary/timeseries; CSV/JSON; totals included.
- **Auditing** — Create/update/delete logged with diffs and request metadata.
- **Webhooks** — Queue + worker command; HTTPS/signature requirements via env flags.
- **Throttling** — Global (`user`, `anon`) and named scopes (seed wizard, exports, public labels, imports, reports…).
- **Observability** — Request-ID middleware logs one structured line per request with latency.

---

## Architecture Overview

```text
┌────────────┐     ┌──────────────┐     ┌───────────────┐
│  Browser   │────▶│  SessionAuth │────▶│  DRF ViewSets │───────────────┐
│/API client │     │ + CSRF       │     │  + mixins     │               │
└────────────┘     └──────────────┘     └──────┬────────┘               │
                                               │                        │
                   Filters/Search/Ordering/Pagination                   │
                                               │                        ▼
                                    ┌──────────┴──────────┐     ┌───────────────┐
                                    │   Serializers       │◀───▶│   Models      │
                                    │ (validation)        │     │ (OwnedModel)  │
                                    └──────────┬──────────┘     └──────┬────────┘
                                               │                       │
                          Concurrency (ETag/If-Match) & Idempotency    │
                                               │                       │
                                               ▼                       ▼
                                    ┌──────────┴──────────┐     ┌───────────────┐
                                    │  Signals/Auditing   │     │  Webhook Queue│
                                    │  Labels, revocations│     │  Worker cmd   │
                                    └─────────────────────┘     └───────────────┘
````

* **Tenancy** enforced by owner-scoped querysets + `IsOwner`.
* **Concurrency** via ETag/If-Match helpers; **Idempotency** decorator caches first success.
* **Public surface** for labels at `/p/<token>/` (no auth) with analytics.

---

## Project Layout

```text
NurseryApp/
├─ accounts/                        # Custom User model
├─ core/
│  ├─ models.py                     # OwnedModel / OwnedQuerySet
│  ├─ permissions.py                # IsOwner object guard
│  ├─ throttling.py                 # Global + named scopes
│  ├─ utils/
│  │  ├─ idempotency.py             # @idempotent decorator
│  │  ├─ concurrency.py             # ETag helpers + If-Match guard
│  │  └─ webhooks.py                # enqueue/signing helpers
│  ├─ middleware.py                 # Request-ID logging
│  └─ views.py                      # /health/
├─ nursery/
│  ├─ models.py                     # Taxon, Material, Batch, Plant, Event, Label*, Audit*, Webhook*
│  ├─ serializers.py                # Model serializers + custom fields/DTOs
│  ├─ api/
│  │  ├─ viewsets.py                # Owner-scoped CRUD
│  │  ├─ labels.py                  # create/rotate/revoke/qr/stats
│  │  ├─ batch_ops.py               # harvest/cull/complete/archive
│  │  ├─ plant_ops.py               # bulk status + archive
│  │  ├─ events_export.py           # events export (CSV/JSON)
│  │  ├─ imports.py                 # CSV endpoints
│  │  ├─ reports.py                 # inventory & production
│  │  ├─ audit.py                   # audit read-only
│  │  ├─ wizard_seed.py             # stepwise seed wizard
│  │  └─ v1_aliases.py              # /api/v1/ router mirror
│  ├─ public_views.py               # /p/<token>/ & /p/<token>/qr.svg
│  ├─ renderers.py                  # CSV renderer
│  ├─ schema.py                     # drf-spectacular extensions
│  ├─ signals.py                    # label lifecycle + webhook emits
│  ├─ audit_hooks.py                # soft-delete -> audit delete
│  └─ management/commands/
│     ├─ dev_seed.py                # developer data (idempotent)
│     ├─ deliver_webhooks.py        # webhook worker
│     └─ cleanup_idempotency.py     # vacuums stale entries
├─ nursery_tracker/
│  ├─ settings/{base,dev,prod}.py   # 12-factor split
│  └─ urls.py                       # routers, docs, public, health
├─ templates/public/label_detail.html
└─ frontend/                        # React + TS (Vite) app
   └─ src/
      ├─ api/                       # http.ts + auth.ts (+ tests)
      ├─ auth/                      # AuthContext + RequireAuth + LogoutButton
      ├─ pages/                     # Login, Register, Forgot/Reset, PasswordChange, Home
      ├─ test/                      # Vitest setup & tests
      ├─ App.tsx, main.tsx
      └─ vite.config.ts, tsconfig.json, index.html, package.json
```

---

## Getting Started

**Prereqs**

* Python **3.12+**
* Node.js **18+** (front-end dev)
* SQLite (dev default) or PostgreSQL 14+ (recommended for prod)

**Backend setup**

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt

# First run
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

**Frontend setup**

```bash
cd frontend
npm ci
npm run dev
# Vite serves at http://localhost:5173 by default (will pick 5174 if busy)
```

---

## Configuration (Backend)

Key environment variables (12-factor):

| Variable                  | Purpose                                    | Typical Dev                                          |
| ------------------------- | ------------------------------------------ | ---------------------------------------------------- |
| `DEBUG`                   | Debug mode                                 | `True`                                               |
| `SECRET_KEY`              | Django secret                              | `dev-change-me`                                      |
| `DATABASE_URL`            | DB connection string                       | `sqlite:///db.sqlite3`                               |
| `ALLOWED_HOSTS`           | Host allowlist                             | `127.0.0.1,localhost`                                |
| `CSRF_TRUSTED_ORIGINS`    | Scheme+host for CSRF origin/referer checks | include backend (8000) and frontend (5173/5174)      |
| `CSRF_COOKIE_HTTPONLY`    | Must be **False** for SPA                  | `False` in dev (frontend must read `csrftoken`)      |
| `CSRF_COOKIE_SAMESITE`    | Cookie SameSite                            | `Lax`                                                |
| `SESSION_COOKIE_SAMESITE` | Cookie SameSite                            | `Lax`                                                |
| `ENFORCE_IF_MATCH`        | Require `If-Match` on write                | `False` (dev)                                        |
| `ENABLE_REGISTRATION`     | Toggle `/auth/register/`                   | `True` in dev, `False` in prod (recommended default) |
| `MAX_REQUEST_BYTES`       | Request body cap                           | optional                                             |
| `MAX_IMPORT_BYTES`        | CSV upload cap (bytes)                     | `5000000`                                            |
| `IMPORT_MAX_ROWS`         | Max rows per import                        | `50000`                                              |
| `EXPORT_MAX_ROWS`         | Row cap for exports                        | optional                                             |
| `WEBHOOKS_*`              | HTTPS/signature/UA/backoff/limits          | see settings                                         |

> **Important (dev):** Ensure `CSRF_TRUSTED_ORIGINS` includes `http://localhost:5173` and `http://localhost:5174` (and their `127.0.0.1` equivalents) if Vite switches ports.

---

## Frontend (React + TypeScript + Vite)

This frontend is a minimal, production-clean **Auth slice** that talks to the backend via the **`/api/v1/`** mirror using **session cookies + CSRF**. It provides a guarded application shell (`RequireAuth`) and public auth pages.

### Folder Layout

```
frontend/
└─ src/
   ├─ api/
   │  ├─ http.ts         # fetch wrapper: base '/api/v1/', credentials: 'include', CSRF header on unsafe
   │  ├─ auth.ts         # getCsrf, login, logout, me, register?, password reset & change
   │  └─ auth.test.ts    # unit tests (vitest) for client
   ├─ auth/
   │  ├─ AuthContext.tsx # { user, hydrated, refresh, logout } (hydrates on mount via me())
   │  ├─ RequireAuth.tsx # gate that redirects to /login?next=...
   │  └─ LogoutButton.tsx# shared logout with CSRF prime, safe navigation
   ├─ pages/
   │  ├─ Login.tsx
   │  ├─ Register.tsx          # shown only if backend registration enabled (403/404 → friendly msg)
   │  ├─ ForgotPassword.tsx
   │  ├─ ResetPassword.tsx
   │  ├─ PasswordChange.tsx    # authenticated
   │  └─ Home.tsx              # example protected page
   ├─ test/                # vitest setup and integration tests
   ├─ App.tsx              # router: public auth routes; protected app routes in <RequireAuth>
   └─ main.tsx
```

### Running the Frontend

```bash
cd frontend
npm ci
npm run dev
# -> http://localhost:5173 (or 5174 if 5173 is busy)
```

`vite.config.ts` proxies `/api` to `http://127.0.0.1:8000`, preserving cookies:

```ts
server: {
  port: 5173,
  // strictPort: true, // Optional: lock port to avoid CSRF trusted-origin churn
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
      cookieDomainRewrite: '', // keep cookies first-party
    },
  },
},
```

### API Client Conventions

* **Base URL:** `/api/v1/` (v1 mirror).
* **Credentials:** all requests use `credentials: 'include'`.
* **CSRF:** Unsafe methods (POST/PATCH/PUT/DELETE) attach `X-CSRFToken` from cookie **csrftoken**.
* **Errors:** Decode from DRF standard `{ "detail": "...", "code"?: "..." }`; fallback to HTTP status text.

**Endpoints (session-based, CSRF required on unsafe):**

```
GET  /auth/csrf/                      -> 204 (sets csrftoken cookie)
POST /auth/login/                     -> 200 {"id","username","email"} (sets session)
POST /auth/logout/                    -> 204 (clears session)
GET  /auth/me/                        -> 200 or 401

POST /auth/password/reset/            -> 204
POST /auth/password/reset/confirm/    -> 204
POST /auth/password/change/           -> 204

POST /auth/register/                  -> 201/204 (if ENABLE_REGISTRATION=True)
```

> **Important:** Do not disable CSRF. The frontend first calls `getCsrf()` (or any GET) to receive the cookie, then attaches `X-CSRFToken` for unsafe requests.

### Auth Flow (Pages & Components)

* **Auth Shell**

  * `AuthContext` hydrates on mount via `me()`. Exposes `{ user, hydrated, refresh, logout }`.
  * `RequireAuth` redirects unauthenticated users to `/login?next=...`.
  * `AppLayout` header shows `{username}` + unified **Logout** button.

* **Login**

  * Fields: `username`, `password`.
  * Flow: `await getCsrf()`, `await login()`, `await refresh()` → navigate to `next` or `/`.
  * Errors:

    * 400/401 → “Invalid username or password.”
    * 429 → “Too many attempts; please wait.”

* **Register** (optional)

  * Requires email (`username`, `email`, `password1`, `password2`).
  * If backend returns 403/404, show “Registration is currently disabled.”

* **Forgot/Reset**

  * `POST /auth/password/reset/` → 204.
  * `POST /auth/password/reset/confirm/` with `{ uid, token, new_password1, new_password2 }` → 204.

* **Password Change** (authenticated)

  * `POST /auth/password/change/` with `{ old_password, new_password1, new_password2 }` → 204.

### Testing (Frontend)

```bash
cd frontend
npm test      # vitest
npm run typecheck
```

* Unit tests for `src/api/http.ts` and `src/api/auth.ts` (mock fetch).
* Integration tests for `RequireAuth` & auth pages.

### Common Frontend Pitfalls

* **403 on login/logout/register (CSRF):**

  * Ensure `X-CSRFToken` is sent. In dev, `CSRF_COOKIE_HTTPONLY` must be **False** so the SPA can read `csrftoken`.
  * Ensure `CSRF_TRUSTED_ORIGINS` includes your dev origin (e.g., `http://localhost:5173` and `http://localhost:5174` if Vite changed ports).
  * Consider `strictPort: true` in Vite to prevent port drift.

* **Two logout buttons, one fails:**

  * Always use the shared `<LogoutButton />`, which primes CSRF and calls `AuthContext.logout()`.

* **Missing v1 routes:**

  * Frontend must call `/api/v1/`. Confirm the v1 router mirror is mounted.

---

## API Docs & URLs

* **API root**: `http://127.0.0.1:8000/api/`
* **v1 mirror**: `http://127.0.0.1:8000/api/v1/` (same handlers, frozen surface)
* **OpenAPI schema**: `http://127.0.0.1:8000/api/schema/`
* **Swagger UI**: `http://127.0.0.1:8000/api/docs/`
* **Redoc**: `http://127.0.0.1:8000/api/redoc/`
* **Admin**: `http://127.0.0.1:8000/admin/`
* **Health**: `http://127.0.0.1:8000/health/`
* **Public label page**: `http://127.0.0.1:8000/p/<RAW_TOKEN>/`

---

## Security & Tenancy

* **Authentication**: `SessionAuthentication` (Django sessions).
* **CSRF**: Required for POST/PUT/PATCH/DELETE. Obtain cookie via GET, then send `X-CSRFToken`.
* **Tenancy**: Domain models derive from a common owned base (`user`, timestamps). Querysets are scoped by `request.user`. Object access is enforced by a strict owner permission.
* **Public endpoints**: Only the label public page (`/p/<token>/` and its SVG) is anonymous; responses contain minimal fields.

---

## Domain Model

* **Taxon** — identity is the triple *(scientific\_name, cultivar?, clone\_code?)*, unique **per user**.
* **PlantMaterial** — FK→Taxon; `material_type` (Seed/Cutting/…); optional `lot_code`; provenance notes.
* **PropagationBatch** — FK→PlantMaterial; `method`, `status`, `quantity_started`, `started_on`.
* **Plant** — FK→Taxon; optional FK→PropagationBatch; `status`, `quantity`, `acquired_on`; **soft-deletable**.
* **Event** — Targets **exactly one** of `batch` XOR `plant`; `event_type`, `happened_at`, `quantity_delta?`, `notes?`.
* **Label** — Generic to Plant/Batch/Material; may have a single `active_token`.
* **LabelToken** — Stored **as hash + prefix only**; `revoked_at` marks rotation/revocation; raw token is shown once.
* **LabelVisit** — Captures public page hits (for owner analytics).
* **AuditLog** — Immutable audit trail (model, action, changes, request metadata).
* **WebhookEndpoint / WebhookDelivery** — Outbound webhooks configuration & queued deliveries.

**Relationships (simplified)**

```text
Taxon 1─* PlantMaterial 1─* PropagationBatch 1─* Plant
Event → (exactly one of) {PropagationBatch | Plant}
Label → GenericForeignKey to {Plant, PropagationBatch, PlantMaterial}
```

---

## Core API Endpoints

Owner-scoped CRUD with filtering/search/ordering/pagination:

* `GET/POST /api/taxa/`
* `GET/POST /api/materials/`
* `GET/POST /api/batches/`
* `GET/POST /api/plants/`
* `GET/POST /api/events/`

**Soft delete / archive**:

* `POST /api/plants/{id}/archive/`
* `POST /api/batches/{id}/archive/`

> Hard DELETE is not supported for Plants/Batches to preserve history and labels.

---

## Seed Wizard

Throttled under scope **`wizard-seed`**. Stepwise flow:

* `POST /api/wizard/seed/select-taxon/`
* `POST /api/wizard/seed/create-material/`
* `POST /api/wizard/seed/create-batch/`
* `POST /api/wizard/seed/log-sow/`
* `POST /api/wizard/seed/compose/` — one-shot compose of all steps (idempotent)

---

## Labels, QR & Public Pages

* **Create**
  `POST /api/labels/`
  Body:

  ```json
  { "target": { "type": "plant|batch|material", "id": 123 } }
  ```

  Returns **once**: `{ "token": "<RAW>", "public_url": "/p/<RAW>/" , ... }`

* **Rotate** — revoke current, return new raw token
  `POST /api/labels/{id}/rotate/`

* **Revoke** — revoke active token (safe to repeat)
  `POST /api/labels/{id}/revoke/`

* **Owner QR** (requires proof-of-possession)
  `GET /api/labels/{id}/qr/?token=<RAW>` → SVG, `Cache-Control: no-store`

* **Public page**
  `GET /p/<RAW>/` → HTML summary; records a `LabelVisit`

* **Public QR**
  `GET /p/<RAW>/qr.svg` → SVG URL encoder, **immutable cache** (no secrets inside)

* **Stats**
  `GET /api/labels/{id}/stats/?days=N`

  * Without `days`: `{ total_visits, last_7d, last_30d }`
  * With `days` (1–365): adds `{ window_days, start_date, end_date, series:[{date, visits}] }`

**Token privacy**: Raw tokens are never persisted; only a SHA-256 hash and a short prefix are stored. Plants moved to terminal status (e.g., **SOLD/DEAD/DISCARDED**) automatically revoke/detach the active token.

---

## Bulk Operations

* **Plants — bulk status**
  `POST /api/plants/bulk/status/`
  Body:

  ```json
  { "ids": [1,2,3], "status": "SOLD", "notes": "Market sale" }
  ```

  Emits per-plant `Event` rows; response includes updated/missing/event IDs.

* **Batches — inventory lifecycle**

  * `POST /api/batches/{id}/harvest/` → creates a Plant (+quantity) and records a batch `POT_UP` event (−quantity)
  * `POST /api/batches/{id}/cull/` → records negative `quantity_delta`
  * `POST /api/batches/{id}/complete/` → requires zero remaining unless `force=true`
  * `POST /api/batches/{id}/archive/` → soft delete; revokes labels

All above honor idempotency; writes can be protected with `If-Match` (see below).

---

## Exports

**Events** export (throttled: `events-export`):

* `GET /api/events/export/?format=csv|json`
* **CSV headers**:

  ```
  id,happened_at,event_type,target_type,batch_id,plant_id,quantity_delta,notes
  ```
* **JSON** returns a non-paginated list.
* When row-capped, responses include:

  * `X-Export-Total`, `X-Export-Limit`, `X-Export-Truncated: true`

Content negotiation supports `Accept: text/csv` as an alternative to `?format=csv`.

---

## Imports

CSV multipart endpoints (throttled: `imports`) with row/size caps and optional dry-run:

* `POST /api/imports/taxa/`
  Columns: `scientific_name,cultivar,clone_code`

* `POST /api/imports/materials/`
  Columns: `taxon_id,material_type,lot_code,notes`

* `POST /api/imports/plants/?dry_run=1`
  Columns: `taxon_id,batch_id?,status?,quantity?,acquired_on?,notes?`
  (choices accept canonical values or case-insensitive labels)

**Limits**:

* Upload > `MAX_IMPORT_BYTES` → **413** with JSON error
* Data rows > `IMPORT_MAX_ROWS` → remaining rows are ignored (processed count reflects the cap)

---

## Reports

Owner-scoped; throttled: `reports-read`.

* **Inventory** — `/api/reports/inventory/?format=json|csv`
  JSON includes `rows` and `totals`. CSV includes a totals footer.

* **Production** — `/api/reports/production/?from=YYYY-MM-DD&to=YYYY-MM-DD&format=json|csv&group_by=day?`
  Returns `summary_by_type` and optional `timeseries` when grouped by day.

---

## Idempotency

Send a stable key for any POST that should be safe to retry:

```
Idempotency-Key: <client-generated-uuid-or-hash>
```

The first successful response for `(user, method, path, body-hash)` is cached and **replayed** on duplicates.
(Used by: seed compose, labels create/rotate, bulk ops, imports… as applicable.)

**cURL example**

```bash
curl -i -X POST http://127.0.0.1:8000/api/labels/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 1f2b2f2a-..." \
  -d '{"target":{"type":"plant","id":123}}'
```

---

## Optimistic Concurrency

* **GET detail** returns an `ETag`.
* **PUT/PATCH/DELETE** require `If-Match: <etag>` when `ENFORCE_IF_MATCH=True`.
* Stale tags yield **412 Precondition Failed** and include the expected ETag.

**cURL example**

```bash
# 1) Read current ETag
etag=$(curl -si http://127.0.0.1:8000/api/plants/42/ | awk '/^ETag:/{print $2}')

# 2) Update with If-Match
curl -i -X PATCH http://127.0.0.1:8000/api/plants/42/ \
  -H "Content-Type: application/json" \
  -H "If-Match: $etag" \
  -d '{"notes":"updated"}'
```

---

## Audit Logs

Read-only, owner-scoped listing with filters:

* `GET /api/audit/`
* Query params: `model`, `action`, and date ranges

Each item includes `model`, `action` (`create|update|delete`), `changes` (two-element `[old,new]`), and request metadata (`request_id`, `actor`, IP, user agent).
Soft-deletes (archive) are recorded as `delete`.

---

## Webhooks (Outbound)

* **Endpoints**: per-user configuration (URL, secret, event types, is\_active)
* **Enqueue**: emitted by signals when enabled
* **Deliver**: worker command with retry/backoff

```bash
python manage.py deliver_webhooks
```

**Config flags** (see settings):

* Require HTTPS; custom signature header; user-agent
* Backoff schedule & max attempts
* Toggle auto-emit in dev/test

---

## Health, Throttling, Observability

* **Health** — `/health/` returns DB status (200 or 503)

* **Throttling** — global (`user`, `anon`) and named scopes:
  `wizard-seed`, `events-export`, `label-public`, `imports`, `reports-read`, `audit-read`, `labels-read`

* **Observability** — Request-ID middleware:

  * Adds `X-Request-ID` to every response (respects safe client-provided values)
  * Logs **one** structured line, e.g.:

    ```
    level=INFO logger=nursery.request request_id=... method=GET path=/api/taxa/ status=200 user_id=1 duration_ms=23
    ```

* **Request size limits** — oversize bodies → **413** with:

  ```json
  {"detail": "Request body too large.", "code": "request_too_large"}
  ```

---

## Versioning

* Primary surface: **`/api/`**
* Mirror: **`/api/v1/`** mounted without code duplication (frozen surface)
* OpenAPI advertises both; duplicate operation IDs are safely suffixed
* **Frontend calls `/api/v1/` only**

---

## Testing (Backend)

```bash
python manage.py check
python manage.py test -v 2
```

Coverage includes models (constraints/invariants), auth/ownership, filters & ordering,
bulk ops, import/export (CSV/JSON), reports, labels & analytics, concurrency, throttling,
observability, limits, audit logs, and webhook worker behavior.

---

## Developer Seed & Reset

Start fresh:

```bash
rm -f db.sqlite3
python manage.py migrate
python manage.py dev_seed --reset --size=MEDIUM
```

The developer seed is **idempotent** and creates a linked dataset for exploration.
Check command output for any sample users it creates.

---

## Troubleshooting

* **403 “CSRF Failed” on login/logout/register**

  * Confirm `X-CSRFToken` header is sent for unsafe requests.
  * In dev, ensure `CSRF_COOKIE_HTTPONLY=False` and `CSRF_TRUSTED_ORIGINS` includes your current Vite port (`5173` and **`5174`** if Vite moved).
  * Consider `strictPort: true` in `vite.config.ts`.
* **401/403 on `/auth/me/`**

  * You’re not logged in or session expired. The `AuthContext` treats 401/403 as unauthenticated and redirects via `RequireAuth`.
* **412 Precondition Failed**

  * ETag mismatch. Refresh resource (GET) and retry write with `If-Match`.
* **429 Too Many Requests**

  * Throttle exceeded. Back off; see throttle names/rates in settings and `core/throttling.py`.
* **413 Request Entity Too Large**

  * Increase `MAX_IMPORT_BYTES` or split the file.
* **Vite started on a different port**

  * Add the origin to `CSRF_TRUSTED_ORIGINS` or lock port via `strictPort: true`.

---

## License

MIT (if present).

````

Post-Checks:
- Save this README at the repo root as `README.md`.
- Verify commands by running:
  ```bash
  python manage.py check && python manage.py test
  cd frontend && npm test && npm run dev
````

* Open `http://localhost:5173` (or 5174) and confirm the login → protected home → logout flow.
