from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

# Core API ViewSets
from nursery.api import (
    TaxonViewSet,
    PlantMaterialViewSet,
    PropagationBatchViewSet,
    PlantViewSet,
    EventViewSet,
    WizardSeedViewSet,
)

# Labels (ensure this import is present)
from nursery.api.labels import LabelViewSet

# Audit API
from nursery.api.audit import AuditLogViewSet

# Standalone views
from nursery.exports import EventsExportView
from nursery.public_views import PublicLabelView

router = DefaultRouter()
router.register(r"taxa", TaxonViewSet, basename="taxon")
router.register(r"materials", PlantMaterialViewSet, basename="plantmaterial")
router.register(r"batches", PropagationBatchViewSet, basename="propagationbatch")
router.register(r"plants", PlantViewSet, basename="plant")
router.register(r"events", EventViewSet, basename="event")
router.register(r"wizard/seed", WizardSeedViewSet, basename="wizard-seed")
router.register(r"labels", LabelViewSet, basename="label")         # <-- restored
router.register(r"audit", AuditLogViewSet, basename="audit")

urlpatterns = [
    path("admin/", admin.site.urls),

    # OpenAPI / Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

    # Public label page (by token)
    path("p/<slug:token>/", PublicLabelView.as_view(), name="label-public"),

    # API routes (router)
    path("api/", include(router.urls)),

    # Canonical events export
    path("api/events/export/", EventsExportView.as_view(), name="event-export"),
]
