from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from nursery.api import (
    TaxonViewSet,
    PlantMaterialViewSet,
    PropagationBatchViewSet,
    PlantViewSet,
    EventViewSet,
    WizardSeedViewSet,
)
from nursery.api.labels import LabelViewSet
from nursery.api.audit import AuditLogViewSet
from nursery.api.imports import TaxaImportView, MaterialsImportView, PlantsImportView
from nursery.api.reports import InventoryReportView, ProductionReportView
from nursery.exports import EventsExportView
from nursery.public_views import PublicLabelView

router = DefaultRouter()
router.register(r"taxa", TaxonViewSet, basename="taxon")
router.register(r"materials", PlantMaterialViewSet, basename="plantmaterial")
router.register(r"batches", PropagationBatchViewSet, basename="propagationbatch")
router.register(r"plants", PlantViewSet, basename="plant")
router.register(r"events", EventViewSet, basename="event")
router.register(r"wizard/seed", WizardSeedViewSet, basename="wizard-seed")
router.register(r"labels", LabelViewSet, basename="label")
router.register(r"audit", AuditLogViewSet, basename="audit")

urlpatterns = [
    path("admin/", admin.site.urls),

    # OpenAPI / Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

    # ---- Standalone endpoints must come BEFORE the router include ----
    # Events export (canonical)
    path("api/events/export/", EventsExportView.as_view(), name="event-export"),

    # Reports
    path("api/reports/inventory/", InventoryReportView.as_view(), name="report-inventory"),
    path("api/reports/production/", ProductionReportView.as_view(), name="report-production"),

    # Imports
    path("api/imports/taxa/", TaxaImportView.as_view(), name="import-taxa"),
    path("api/imports/materials/", MaterialsImportView.as_view(), name="import-materials"),
    path("api/imports/plants/", PlantsImportView.as_view(), name="import-plants"),

    # Public label page (by token)
    path("p/<slug:token>/", PublicLabelView.as_view(), name="label-public"),

    # Router-driven CRUD/API
    path("api/", include(router.urls)),
]
