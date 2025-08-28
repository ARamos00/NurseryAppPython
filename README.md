# Nursery Tracker — Django/DRF backend

A production-grade **Django 5.2 + Django REST Framework 3.16** backend for tracking nursery operations:
**taxa**, **plant materials**, **propagation batches**, **plants**, **events** — with
**per-user tenancy**, **SessionAuth + CSRF**, **OpenAPI docs**, **throttling**, **idempotency**,
**optimistic concurrency (ETag/If-Match)**, **bulk ops**, **CSV imports/exports**, **reports**,
**QR labels + public pages**, **auditing**, and **outbound webhooks**.

> The API is the product surface. A separate UI can be layered on later without changing contracts.

---

## Table of Contents

- [Highlights](#highlights)
- [Architecture Overview](#architecture-overview)
- [Project Layout](#project-layout)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Runbook](#runbook)
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
- [Testing](#testing)
- [Developer Seed & Reset](#developer-seed--reset)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Highlights

- **Per-user tenancy** — All domain models subclass `core.OwnedModel` and are scoped by `request.user`.
- **Session auth + CSRF** — Browser-friendly, production-safe defaults. CSRF is required for unsafe methods.
- **OpenAPI 3** — drf-spectacular with Swagger UI & Redoc. Custom components for concurrency/idempotency headers.
- **Idempotency** — Safe retries for POST using `Idempotency-Key`; first success is cached and replayed.
- **Optimistic concurrency** — ETag on GET; `If-Match` required on write (when enabled), 412 on stale.
- **Labels & public pages** — Rotatable/revocable tokens, owner/public QR SVG endpoints, visit analytics.
- **Bulk ops** — Plant bulk status updates; batch harvest/cull/complete; archive (soft delete) for plants/batches.
- **CSV imports/exports** — Events export (CSV/JSON). CSV imports for taxa/materials/plants with dry-run.
- **Reports** — Inventory snapshot and production summary/timeseries; CSV/JSON; totals included.
- **Auditing** — Create/update/delete logged with diffs and request metadata.
- **Webhooks** — Queue + worker command; HTTPS/signature requirements governed by env flags.
- **Throttling** — Global (`user`, `anon`) and named scopes (seed wizard, exports, public labels, imports, reports…).
- **Observability** — Request-ID middleware adds `X-Request-ID` and logs one structured line per request.
- **Limits** — Request/upload size guards return consistent **413** JSON.

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

* **Tenancy** enforced by `OwnedModel` + `IsOwner`.
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
└─ templates/public/label_detail.html
```

---

## Getting Started

**Prereqs**

* Python **3.12+**
* SQLite (dev default) or PostgreSQL 14+ (recommended for prod)

**Setup**

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env                 # Or create .env using the table below
```

---

## Configuration

The app is 12-factor friendly. Key environment variables:

| Variable                      | Purpose                           | Typical Dev             |
| ----------------------------- | --------------------------------- | ----------------------- |
| `DEBUG`                       | Enable debug mode                 | `True`                  |
| `SECRET_KEY`                  | Django secret                     | `dev-change-me`         |
| `DATABASE_URL`                | DB connection string              | `sqlite:///db.sqlite3`  |
| `ALLOWED_HOSTS`               | Host allowlist                    | `127.0.0.1,localhost`   |
| `CSRF_TRUSTED_ORIGINS`        | Scheme+host for CSRF              | `http://127.0.0.1:8000` |
| `ENFORCE_IF_MATCH`            | Require `If-Match` on write       | `False` (dev)           |
| `MAX_REQUEST_BYTES`           | Request body cap                  | optional                |
| `MAX_IMPORT_BYTES`            | CSV upload cap (bytes)            | `5000000`               |
| `IMPORT_MAX_ROWS`             | Max data rows per import          | `50000`                 |
| `EXPORT_MAX_ROWS`             | Max rows returned by export       | optional                |
| `WEBHOOKS_*`                  | HTTPS/signature/UA/backoff/limits | see settings            |
| `REST_FRAMEWORK["PAGE_SIZE"]` | Default list page size            | `25`                    |

**Throttling rates** (set via env; see `core/throttling.py` for names):

* Global: `user`, `anon`
* Scoped: `wizard-seed`, `events-export`, `label-public`, `imports`, `reports-read`, `audit-read`, `labels-read`

---

## Runbook

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
# (optional) in another terminal: run the webhook worker
python manage.py deliver_webhooks
```

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

* **Authentication**: `SessionAuthentication` with Django sessions.
* **CSRF**: Required for POST/PUT/PATCH/DELETE. Obtain cookie via GET, then send `X-CSRFToken`.
* **Tenancy**: All domain models derive from `OwnedModel` (`user`, `created_at`, `updated_at`). Querysets are scoped by `request.user`. Object access is enforced by `core.permissions.IsOwner`.
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

**Token privacy**: Raw tokens are never persisted; only a SHA-256 hash and a short prefix are stored. Plants moved to a terminal status (e.g., **SOLD/DEAD/DISCARDED**) automatically revoke/detach the active token.

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
  * Logs **one** structured line to the `nursery.request` logger, e.g.:

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

---

## Testing

Run the full suite:

```bash
python manage.py tests -v 2
```

Coverage includes models (constraints/invariants), auth/ownership, filters & ordering,
bulk ops, import/export (CSV/JSON), reports, labels & analytics, concurrency, throttling,
observability, limits, audit logs, and webhook delivery worker behavior.

---

## Developer Seed & Reset

Start fresh:

```bash
rm -f db.sqlite3
python manage.py migrate
python manage.py dev_seed --reset --size=MEDIUM
```

The developer seed is **idempotent** and creates a small, linked dataset for exploration.
Check command output for any sample users it creates.

---

## Troubleshooting

* **403 CSRF** — Perform a GET to set cookies; send `X-CSRFToken` on write.
* **412 Precondition Failed** — Refresh to get the latest `ETag`, then retry with `If-Match`.
* **404 `/p/<token>/`** — Token was rotated/revoked or unknown; create/rotate a label to get a fresh token.
* **429 throttling** — Back off or tune throttle env rates.
* **413 upload** — Increase `MAX_IMPORT_BYTES`, or split files.
* **OpenAPI quirks** — Custom field/headers are documented via `nursery/schema.py`. When adding new enums or actions, ensure names remain unique.

---

## License

MIT (see `LICENSE` if present).

```
```
