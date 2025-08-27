Reasoning Summary:

* We’ve completed A–J polishing (v1 mirror, soft-delete/archive, label analytics + clickable QR, reports polish, imports caps, webhooks worker/flags, observability, limits middleware, docs polish).
* The README is updated to be the single source of truth: architecture, layout, env, runbooks, endpoint reference (with exact shapes), throttle scopes, concurrency/idempotency, and troubleshooting.
* Scope is documentation-only; no runtime behavior changes. Language is precise and aligned with your code/tests.

Planned Changes:

* PATH: `README.md` — Replace with a comprehensive, production-grade document reflecting the current backend.

Artifacts:
PATH: README.md

```markdown
# Nursery Tracker — Backend-First Django/DRF

A production-grade **Django 5.2 + DRF 3.16** backend for tracking nursery operations:
**taxa**, **plant materials**, **propagation batches**, **plants**, **events** — with
**per-user tenancy**, **session auth + CSRF**, **OpenAPI docs**, **throttling**, **idempotency**,
**optimistic concurrency (ETag/If-Match)**, **bulk ops**, **imports/exports**, **reports**,
**QR labels + public pages**, **auditing**, and **outbound webhooks**.

> Backend is the product surface. A UI can be layered later without changing API contracts.

---

## Table of Contents

- [Highlights](#highlights)
- [Architecture](#architecture)
- [Project Layout](#project-layout)
- [Getting Started](#getting-started)
- [Configuration (.env)](#configuration-env)
- [Runbook](#runbook)
- [API Docs & URLs](#api-docs--urls)
- [Security & Tenancy](#security--tenancy)
- [Domain Model](#domain-model)
- [Core API](#core-api)
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
- [Reset & Developer Seed](#reset--developer-seed)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Highlights

- **Per-user tenancy**: All data scoped by `user`; object access guarded by `IsOwner`.
- **Session auth + CSRF**: Production-safe defaults; CSRF enforced on unsafe methods.
- **OpenAPI 3**: Swagger UI & Redoc via drf-spectacular; clean, stable enums and components.
- **Seed wizard**: Guided flow for Seed → Material → Batch → SOW event.
- **Labels & public pages**: Rotatable tokens, QR codes, anonymous public page, visit analytics.
- **Bulk ops**: Plant status updates; batch harvest/cull/complete.
- **Exports/Imports**: Events export (CSV/JSON). CSV imports for taxa/materials/plants with dry-run.
- **Reports**: Inventory snapshot + production summary/timeseries (CSV/JSON) with totals.
- **Idempotency**: Safe retries with `Idempotency-Key`.
- **Optimistic concurrency**: ETag on GET; `If-Match` on write; 412 on stale.
- **Auditing**: Lightweight audit trail of create/update/delete via API path.
- **Webhooks**: Queue + worker for outbound deliveries; feature-flag friendly.
- **Observability**: Request ID middleware with structured logs.
- **Limits**: Request size limiter returns consistent `413` JSON.

---

## Architecture

```

accounts/                 # Custom User (AUTH\_USER\_MODEL)
core/
models.py               # OwnedModel / OwnedQuerySet
permissions.py          # IsOwner object-level guard
throttling.py
utils/
idempotency.py        # @idempotent decorator (header-based)
concurrency.py        # ETag helpers (+ If-Match guard)
webhooks.py           # enqueue(), signing, delivery scaffolding
nursery/
models.py               # Taxon, PlantMaterial, PropagationBatch, Plant, Event
\# Label, LabelToken, LabelVisit, AuditLog
serializers.py          # Model serializers + DTOs (Label target, report shapes)
api/
viewsets.py           # CRUD ViewSets (owner-scoped) + audit writes
wizard\_seed.py        # Seed onboarding (stepwise + compose)
labels.py             # LabelViewSet (create/rotate/revoke/qr/stats)
batch\_ops.py          # harvest / cull / complete / archive
plant\_ops.py          # bulk status / archive
events\_export.py      # events export (CSV/JSON)
imports.py            # CSV imports (taxa/materials/plants)
reports.py            # inventory + production endpoints
audit.py              # read-only audit log viewset (filters)
public\_views.py         # /p/<token>/ and /p/<token>/qr.svg
renderers.py            # PassthroughCSVRenderer (negotiates CSV cleanly)
schema.py               # OpenAPI components + custom field mapping
signals.py              # Label + webhook emits, terminal-state revocations
management/commands/
dev\_seed.py           # idempotent seed
deliver\_webhooks.py   # worker: retry/backoff, DLQ-ready
nursery\_tracker/
settings/base.py dev.py prod.py
urls.py                 # routers, docs, health, public routes
templates/public/label\_detail.html

````

**Tenancy**: domain models subclass `core.OwnedModel` (`user`, `created_at`, `updated_at`).
ViewSets scope querysets by `request.user`; `IsOwner` enforces object access.

---

## Project Layout

```text
NurseryApp/
├─ accounts/                  ┆
├─ core/                      ┆  security, tenancy, utilities
├─ nursery/                   ┆  domain + API
│  └─ tests/                  ┆  comprehensive test suite
└─ nursery_tracker/           ┆  settings & urls
````

---

## Getting Started

### Prereqs

* Python **3.12+**
* SQLite (default dev) or PostgreSQL 14+ (recommended for prod)

### Setup

```bash
python -m venv .venv
source ./.venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env  # or create manually (see below)
```

---

## Configuration (.env)

```ini
DEBUG=True
SECRET_KEY=dev-insecure-change-me
DATABASE_URL=sqlite:///db.sqlite3

ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

# Throttle tuning
DRF_THROTTLE_RATE_USER=200/min
DRF_THROTTLE_RATE_ANON=50/min
DRF_THROTTLE_RATE_WIZARD_SEED=30/min
DRF_THROTTLE_RATE_EVENTS_EXPORT=10/min
DRF_THROTTLE_RATE_LABEL_PUBLIC=120/min
DRF_THROTTLE_RATE_AUDIT_READ=60/min
DRF_THROTTLE_RATE_IMPORTS=6/min
DRF_THROTTLE_RATE_REPORTS_READ=60/min
DRF_THROTTLE_RATE_LABELS_READ=60/min

# Concurrency toggle (require If-Match)
ENFORCE_IF_MATCH=False

# Upload/Import caps (bytes)
MAX_IMPORT_BYTES=5000000

# Webhooks
WEBHOOKS_REQUIRE_HTTPS=False        # True in prod
WEBHOOKS_SIGNATURE_HEADER=X-Webhook-Signature
WEBHOOKS_USER_AGENT=NurseryTracker/0.1
WEBHOOKS_ENABLE_AUTO_EMIT=False
```

See `nursery_tracker/settings/prod.py` for HSTS/SSL production hardening.

---

## Runbook

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
# (optional) start webhook worker in another terminal
python manage.py deliver_webhooks
```

---

## API Docs & URLs

* **API root**: `http://127.0.0.1:8000/api/`
* **v1 mirror**: `http://127.0.0.1:8000/api/v1/` (surface frozen; same handlers)
* **OpenAPI**: `http://127.0.0.1:8000/api/schema/`
* **Swagger UI**: `http://127.0.0.1:8000/api/docs/`
* **Redoc**: `http://127.0.0.1:8000/api/redoc/`
* **Admin**: `http://127.0.0.1:8000/admin/`
* **Health**: `http://127.0.0.1:8000/health/`
* **Public label page**: `http://127.0.0.1:8000/p/<RAW_TOKEN>/`

---

## Security & Tenancy

* **Auth**: `SessionAuthentication` (login via admin/browsable API).
* **CSRF**: required for POST/PUT/PATCH/DELETE. Obtain cookie with a GET first; send `X-CSRFToken`.
* **Tenancy**: models subclass `OwnedModel`; queries filter by `request.user`; `IsOwner` enforces object access.
* **Public pages**: token-based; only minimal fields exposed; label tokens are revocable and rotatable.

---

## Domain Model

* **Taxon** — `scientific_name`, `cultivar?`, `clone_code?`. Unique **per user** across the triple.
* **PlantMaterial** — FK→Taxon; `material_type` (Seed/Cutting/…); `lot_code?`.
* **PropagationBatch** — FK→PlantMaterial; `method`, `status`, `quantity_started`, `started_on`.
* **Plant** — FK→Taxon; optional FK→PropagationBatch; `status`, `quantity`, `acquired_on`.
* **Event** — Actions targeting **XOR**: a batch **or** a plant; `event_type`, `happened_at`, `quantity_delta?`, `notes?`.
* **Label** — Generic to Plant/Batch/Material; may have an `active_token`.
* **LabelToken** — `token_hash` (SHA-256), `prefix`, `revoked_at?` (raw never stored).
* **LabelVisit** — public page analytics.
* **AuditLog** — actor, changes, request metadata.

---

## Core API

CRUD ViewSets (owner scoped), each with filtering/search/ordering/pagination:

* `/api/taxa/`
* `/api/materials/`
* `/api/batches/`
* `/api/plants/`
* `/api/events/`

**Delete**: Hard DELETE is disabled for Plants/Batches — use `POST /api/plants/{id}/archive/` and `POST /api/batches/{id}/archive/`.

---

## Seed Wizard

`/api/wizard/seed/*` (throttled: `wizard-seed`):

* `POST /api/wizard/seed/select-taxon/`
* `POST /api/wizard/seed/create-material/`
* `POST /api/wizard/seed/create-batch/`
* `POST /api/wizard/seed/log-sow/`
* `POST /api/wizard/seed/compose/` (one-shot create; idempotent)

---

## Labels, QR & Public Pages

* `POST /api/labels/`
  Body: `{ "target": { "type": "plant"|"batch"|"material", "id": <int> } }`
  Returns **once**: `{ token, public_url, ... }` (token is not stored).

* `POST /api/labels/{id}/rotate/` → revoke old token; return new raw token.

* `POST /api/labels/{id}/revoke/` → revoke active token (safe to repeat).

* **Owner QR**: `GET /api/labels/{id}/qr/?token=<RAW>` → SVG (clickable <a>, `no-store`).

* **Public page**: `GET /p/<RAW>/` → HTML summary; records a `LabelVisit`.

* **Public QR**: `GET /p/<RAW>/qr.svg` → SVG for the public page.

* **Stats**: `GET /api/labels/{id}/stats/?days=N`

  * No `days`: `{ total_visits, last_7d, last_30d }`
  * With `days` (1–365): adds `{ window_days, start_date, end_date, series: [{ date, visits }, ...] }`

**Terminal status** (`SOLD|DEAD|DISCARDED`) on a Plant automatically revokes the active label.

---

## Bulk Operations

* **Plants**: `POST /api/plants/bulk/status/`
  Body: `{ "ids": [1,2], "status": "SOLD", "notes": "Market sale" }`
  Emits appropriate `Event` rows; response includes updated/missing/event IDs.

* **Batches**:

  * `POST /api/batches/{id}/harvest/` → create plant/outtake; negative `quantity_delta` on batch, positive on plant.
  * `POST /api/batches/{id}/cull/` → negative `quantity_delta` (loss/waste).
  * `POST /api/batches/{id}/complete/` → requires zero remaining unless `force=true`.
  * `POST /api/batches/{id}/archive/` → soft-delete; revokes labels.

All ops are idempotent and respect `If-Match` (when enforced).

---

## Exports

**Events**: `GET /api/events/export/?format=csv|json`
CSV headers:

```
id,happened_at,event_type,target_type,batch_id,plant_id,quantity_delta,notes
```

JSON returns a non-paginated list.

---

## Imports

CSV multipart endpoints (throttled: `imports`), with `?dry_run=1` support for plants:

* `POST /api/imports/taxa/`
  `scientific_name,cultivar,clone_code`
* `POST /api/imports/materials/`
  `taxon_scientific_name,material_type,lot_code,notes`
* `POST /api/imports/plants/?dry_run=1`
  `scientific_name,batch_id,quantity,acquired_on,notes,status`

**Size limits**: uploads exceeding `MAX_IMPORT_BYTES` (default 5 MB) return **413** with JSON.

---

## Reports

`/api/reports/*` (owner-scoped; throttled: `reports-read`)

* **Inventory**: `GET /api/reports/inventory/?format=json|csv`

  * JSON includes `meta.totals`; CSV appends totals as a footer comment.
* **Production**: `GET /api/reports/production/?from=YYYY-MM-DD&to=YYYY-MM-DD&format=json|csv`

  * Summary + time series; same totals conventions.

---

## Idempotency

Endpoints marked idempotent accept:

```
Idempotency-Key: <client-generated-stable-key>
```

The first successful response for `(user, method, path, body-hash)` is replayed on retries.

---

## Optimistic Concurrency

* **GET detail** returns `ETag`.
* **PUT/PATCH/DELETE** require `If-Match` when `ENFORCE_IF_MATCH=True`.
  Stale tags return **412 Precondition Failed**.

---

## Audit Logs

Read-only, owner-scoped (staff may filter by `user_id`).
`GET /api/audit-logs/?model=plant&action=update&date_from=...&date_to=...`

Items include:

* `model` (e.g., `"plant"`)
* `action` (`create|update|delete`)
* `changes` (diff), `actor`, `request_id`, `ip`, `user_agent`, timestamps.

---

## Webhooks (Outbound)

* Emitted by signals when enabled; enqueued with metadata/signature.
* Delivered by worker:

```bash
python manage.py deliver_webhooks
```

Environment toggles in `.env` (require HTTPS, signature header, enable auto-emit).
Failures back off and can move to DLQ (scaffolding included).

---

## Health, Throttling, Observability

* **Health**: `/health/` returns DB status (200 or 503).
* **Throttles**:

  * Global: `user`, `anon`
  * Scoped: `wizard-seed`, `events-export`, `label-public`, `audit-read`, `imports`, `reports-read`, `labels-read`
* **Observability**:

  * Request ID middleware logs one JSON-ish line per request with
    `request_id`, `user_id`, `method`, `path`, `status`, `duration_ms`.

Example log:

```
level=INFO logger=nursery.request request_id=... method=GET path=/api/taxa/ status=200 user_id=1 duration_ms=23
```

* **Request size limits**: oversize bodies return **413** with:

  ```json
  {"detail": "Request body too large.", "code": "request_too_large"}
  ```

---

## Versioning

* **/api/** is the primary surface.
* **/api/v1/** is a frozen mirror of the current routes (mounted without code duplication).
* OpenAPI advertises both servers; duplicate `operationId`s are suffixed automatically.

---

## Testing

```bash
python manage.py test -v 2
```

Coverage includes models (constraints), API auth/ownership, filters/ordering,
bulk ops, exports/imports, reports (CSV/JSON), labels + analytics, concurrency,
throttling, docs, limits, and webhooks scaffolding.

---

## Reset & Developer Seed

Fresh run:

```bash
rm -f db.sqlite3
python manage.py migrate
python manage.py dev_seed --reset --size=MEDIUM
```

Users (dev seed): `alice`, `bob` (password: `pass12345`).

---

## Troubleshooting

* **403 CSRF**: Perform a GET to set cookies; send `X-CSRFToken` header on write.
* **412 on update**: Refresh resource to get latest `ETag`; resend with `If-Match`.
* **404 on `/p/<token>/`**: Token revoked or unknown; rotate or create a new label.
* **429 throttling**: Back off or tune env throttles.
* **Docs warnings**: We set `ENUM_NAME_OVERRIDES` and unique component names for custom action responses. If you add enums or new custom actions, keep names unique in `schema.py`.
* **413 upload**: Increase `MAX_IMPORT_BYTES`, or split files.

---

## License

MIT (see `LICENSE` if present).

```

Post-Checks:
- No runtime changes; only `README.md`.  
- Verify the README matches behavior by opening `/api/docs` and spot-checking a few flows:
  - Create a taxon; list taxa.
  - Create a label; fetch owner QR (`/api/labels/{id}/qr/?token=...`).
  - Public page loads for the token (`/p/<token>/`).
  - Events export CSV.
  - Imports reject oversize file with 413 JSON.

Risks & Follow-ups:
- README can drift as features evolve; keep it updated in the same PRs that change routes/contracts.
- When you add DB indexes (performance polish), append a short “Indexes” note under Domain Model with the chosen indices and rationale.
```
