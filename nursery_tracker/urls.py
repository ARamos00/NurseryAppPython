"""
Project URL configuration.

Surfaces
--------
- `/admin/` — Django admin (back-office only).
- `/api/` — primary API surface, router-driven ViewSets (+ standalone endpoints).
- `/api/v1/` — **mirror** of `/api/` without code duplication; endpoints share
  implementations but are mounted under a versioned path for clients.
- `/api/schema`, `/api/docs`, `/api/redoc` — OpenAPI schema & UIs.
- `/p/<token>/` & `/p/<token>/qr.svg` — public label page and QR (AllowAny).

Notes
-----
- Routers are registered once, then included under both `/api/` and `/api/v1/`.
- Public pages are throttled via `label-public` scope in their views.
"""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

# Auth APIViews
from accounts.views import CsrfView, LoginView, LogoutView, MeView

# ViewSets (router-driven)
from nursery.api import (
    TaxonViewSet,
    PlantMaterialViewSet,
    PropagationBatchViewSet,
    PlantViewSet,
    EventViewSet,
    WizardSeedViewSet,
    WebhookEndpointViewSet,
    WebhookDeliveryViewSet,
)
from nursery.api.labels import LabelViewSet
from nursery.api.audit import AuditLogViewSet

# Standalone APIViews (canonical, non-versioned)
from nursery.api.imports import TaxaImportView, MaterialsImportView, PlantsImportView
from nursery.api.reports import InventoryReportView, ProductionReportView
from nursery.exports import EventsExportView

# v1 aliases with method-level schema annotations
from nursery.api.v1_aliases import (
    EventsExportV1View,
    InventoryReportV1View,
    ProductionReportV1View,
    TaxaImportV1View,
    MaterialsImportV1View,
    PlantsImportV1View,
    # Auth v1 wrappers
    CsrfV1View,
    LoginV1View,
    LogoutV1View,
    MeV1View,
)

# Public pages
from nursery.public_views import PublicLabelView, PublicLabelQRView

# ---------------------------------------------------------------------
# Router for current (non-versioned) API
# ---------------------------------------------------------------------
router = DefaultRouter()
router.register(r"taxa", TaxonViewSet, basename="taxon")
router.register(r"materials", PlantMaterialViewSet, basename="plantmaterial")
router.register(r"batches", PropagationBatchViewSet, basename="propagationbatch")
router.register(r"plants", PlantViewSet, basename="plant")
router.register(r"events", EventViewSet, basename="event")
router.register(r"wizard/seed", WizardSeedViewSet, basename="wizard-seed")
router.register(r"labels", LabelViewSet, basename="label")
router.register(r"audit", AuditLogViewSet, basename="audit")
router.register(r"webhooks/endpoints", WebhookEndpointViewSet, basename="wh-endpoint")
router.register(r"webhooks/deliveries", WebhookDeliveryViewSet, basename="wh-delivery")

# ---------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------
urlpatterns = [
    path("admin/", admin.site.urls),

    # OpenAPI / Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

    # --------------------------
    # Auth (canonical)
    # --------------------------
    path("api/auth/csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("api/auth/login/", LoginView.as_view(), name="auth-login"),
    path("api/auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("api/auth/me/", MeView.as_view(), name="auth-me"),

    # Canonical standalone endpoints (current)
    path("api/events/export/", EventsExportView.as_view(), name="event-export"),
    path("api/reports/inventory/", InventoryReportView.as_view(), name="report-inventory"),
    path("api/reports/production/", ProductionReportView.as_view(), name="report-production"),
    path("api/imports/taxa/", TaxaImportView.as_view(), name="import-taxa"),
    path("api/imports/materials/", MaterialsImportView.as_view(), name="import-materials"),
    path("api/imports/plants/", PlantsImportView.as_view(), name="import-plants"),

    # Public label page + QR
    path("p/<slug:token>/", PublicLabelView.as_view(), name="label-public"),
    path("p/<slug:token>/qr.svg", PublicLabelQRView.as_view(), name="label-public-qr"),

    # Router-driven API (current)
    path("api/", include(router.urls)),

    # --------------------------
    # API v1 (frozen surface)
    # --------------------------
    # Auth (v1 mirror)
    path("api/v1/auth/csrf/", CsrfV1View.as_view(), name="auth-csrf-v1"),
    path("api/v1/auth/login/", LoginV1View.as_view(), name="auth-login-v1"),
    path("api/v1/auth/logout/", LogoutV1View.as_view(), name="auth-logout-v1"),
    path("api/v1/auth/me/", MeV1View.as_view(), name="auth-me-v1"),

    # Other v1 wrappers
    path("api/v1/events/export/", EventsExportV1View.as_view(), name="event-export-v1"),
    path("api/v1/reports/inventory/", InventoryReportV1View.as_view(), name="report-inventory-v1"),
    path("api/v1/reports/production/", ProductionReportV1View.as_view(), name="report-production-v1"),
    path("api/v1/imports/taxa/", TaxaImportV1View.as_view(), name="import-taxa-v1"),
    path("api/v1/imports/materials/", MaterialsImportV1View.as_view(), name="import-materials-v1"),
    path("api/v1/imports/plants/", PlantsImportV1View.as_view(), name="import-plants-v1"),

    # v1 router-driven endpoints
    path("api/v1/", include((router.urls, "api_v1"), namespace="api_v1")),
]
