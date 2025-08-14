from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView  # <-- add
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
    LabelViewSet,
)
from nursery.public_views import PublicLabelView

router = DefaultRouter()
router.register(r"taxa", TaxonViewSet, basename="taxon")
router.register(r"materials", PlantMaterialViewSet, basename="plantmaterial")
router.register(r"batches", PropagationBatchViewSet, basename="propagationbatch")
router.register(r"plants", PlantViewSet, basename="plant")
router.register(r"events", EventViewSet, basename="event")
router.register(r"wizard/seed", WizardSeedViewSet, basename="wizard-seed")
router.register(r"labels", LabelViewSet, basename="label")

urlpatterns = [
    # Redirect root to API docs for a friendly landing page
    path("", RedirectView.as_view(pattern_name="swagger-ui", permanent=False)),

    path("admin/", admin.site.urls),

    # OpenAPI / Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

    # API routes
    path("api/", include(router.urls)),

    # Public label page
    path("p/<slug:token>/", PublicLabelView.as_view(), name="label-public"),
]
