from __future__ import annotations

"""
v1 API aliases that mirror canonical endpoints without duplicating logic.

Purpose
-------
- Keep `/api/` as the primary surface while exposing a stable `/api/v1/` mirror.
- These classes only **adjust OpenAPI metadata** (operation ids, summaries,
  response typing) using drf-spectacular; the underlying behavior is identical
  because we subclass the canonical views and call `super()`.

Scope
-----
- Exports: GET `/api/v1/events/export/` mirrors `/api/events/export/`.
- Reports: GET `/api/v1/reports/*` mirror `/api/reports/*`.
- Imports: POST `/api/v1/imports/*` mirror `/api/imports/*`; the multipart file
  request shape is explicitly documented for better Swagger UI UX.
- Auth: GET/POST `/api/v1/auth/*` mirror `/api/auth/*`.

Notes
-----
- We intentionally keep serializers used here "docs-only" to avoid any runtime
  coupling; real response shapes are produced by the canonical endpoints.
"""

from rest_framework import serializers
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes

# Canonical views
from accounts.views import CsrfView, LoginView, LogoutView, MeView
from nursery.exports import EventsExportView
from nursery.api.reports import InventoryReportView, ProductionReportView
from nursery.api.imports import TaxaImportView, MaterialsImportView, PlantsImportView
from nursery.serializers import EventSerializer


# ------------------------------------------------------------------------------
# Docs-only serializer for CSV import results.
# Adjust to match your real JSON envelope if it differs.
# ------------------------------------------------------------------------------
class ImportResultSerializer(serializers.Serializer):
    """Simple schema for import results shown in API docs (not used at runtime)."""
    created = serializers.IntegerField()
    updated = serializers.IntegerField(required=False)
    failed = serializers.IntegerField(required=False)
    errors = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Human-readable error messages per failed row.",
    )


# ------------------------------------------------------------------------------
# Auth (v1 wrappers)
# ------------------------------------------------------------------------------
class CsrfV1View(CsrfView):
    """v1 schema wrapper for the CSRF priming endpoint."""
    @extend_schema(
        operation_id="auth_csrf_v1",
        summary="Prime CSRF cookie (v1 mirror)",
        description=(
            "Mirror of `/api/auth/csrf/`. Returns 204 and sets the CSRF cookie. "
            "Also includes the token in the `X-CSRFToken` response header."
        ),
        responses={204: OpenApiResponse(description="CSRF cookie set")},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class LoginV1View(LoginView):
    """v1 schema wrapper for login."""
    @extend_schema(
        operation_id="auth_login_v1",
        summary="Log in (v1 mirror)",
        responses={
            200: OpenApiResponse(description="Authenticated user JSON"),
            400: OpenApiResponse(description="Invalid credentials"),
            429: OpenApiResponse(description="Too many attempts (throttled)"),
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class LogoutV1View(LogoutView):
    """v1 schema wrapper for logout."""
    @extend_schema(
        operation_id="auth_logout_v1",
        summary="Log out (v1 mirror)",
        responses={204: OpenApiResponse(description="Logged out")},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class MeV1View(MeView):
    """v1 schema wrapper for current user."""
    @extend_schema(
        operation_id="auth_me_v1",
        summary="Current user (v1 mirror)",
        responses={
            200: OpenApiResponse(description="Authenticated user JSON"),
            401: OpenApiResponse(description="Not authenticated"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# ------------------------------------------------------------------------------
# Exports (GET) — mirror of /api/events/export/
# ------------------------------------------------------------------------------
class EventsExportV1View(EventsExportView):
    """
    v1 wrapper that only overrides schema metadata.
    Behavior is identical to the canonical /api/events/export/ endpoint.
    """

    @extend_schema(
        operation_id="events_export_v1",
        summary="Events export (v1 mirror)",
        description=(
            "Exports the current user's events. By default returns CSV. "
            "Pass `?format=json` to receive JSON."
        ),
        parameters=[
            OpenApiParameter(
                name="format",
                type=OpenApiTypes.STR,
                enum=["csv", "json"],
                location=OpenApiParameter.QUERY,
                description="Output format. Default: csv",
            )
        ],
        responses={
            (200, "text/csv"): OpenApiTypes.BINARY,
            (200, "application/json"): EventSerializer(many=True),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# ------------------------------------------------------------------------------
# Reports (GET) — mirrors of /api/reports/*
# ------------------------------------------------------------------------------
class InventoryReportV1View(InventoryReportView):
    """v1 schema wrapper for the inventory report."""
    @extend_schema(
        operation_id="report_inventory_v1",
        summary="Inventory report (v1 mirror)",
        description="Mirror of /api/reports/inventory/ under /api/v1/.",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProductionReportV1View(ProductionReportView):
    """v1 schema wrapper for the production report."""
    @extend_schema(
        operation_id="report_production_v1",
        summary="Production report (v1 mirror)",
        description="Mirror of /api/reports/production/ under /api/v1/.",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# ------------------------------------------------------------------------------
# Imports (POST) — mirrors of /api/imports/*
# ------------------------------------------------------------------------------
_MULTIPART_FILE_REQUEST = {
    "multipart/form-data": {
        "type": "object",
        "properties": {"file": {"type": "string", "format": "binary", "description": "CSV file"}},
        "required": ["file"],
    }
}


class TaxaImportV1View(TaxaImportView):
    """v1 schema wrapper for the taxa import endpoint."""
    @extend_schema(
        operation_id="import_taxa_v1",
        summary="Taxa CSV import (v1 mirror)",
        description="Upload a CSV with taxa. Field name: `file` (multipart/form-data).",
        request=_MULTIPART_FILE_REQUEST,
        responses={201: OpenApiResponse(response=ImportResultSerializer, description="Import result"),
                   400: OpenApiResponse(description="Invalid CSV or validation errors")},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class MaterialsImportV1View(MaterialsImportView):
    """v1 schema wrapper for the materials import endpoint."""
    @extend_schema(
        operation_id="import_materials_v1",
        summary="Materials CSV import (v1 mirror)",
        description="Upload a CSV with plant materials. Field name: `file` (multipart/form-data).",
        request=_MULTIPART_FILE_REQUEST,
        responses={201: OpenApiResponse(response=ImportResultSerializer, description="Import result"),
                   400: OpenApiResponse(description="Invalid CSV or validation errors")},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class PlantsImportV1View(PlantsImportView):
    """v1 schema wrapper for the plants import endpoint."""
    @extend_schema(
        operation_id="import_plants_v1",
        summary="Plants CSV import (v1 mirror)",
        description="Upload a CSV with plants. Field name: `file` (multipart/form-data).",
        request=_MULTIPART_FILE_REQUEST,
        responses={201: OpenApiResponse(response=ImportResultSerializer, description="Import result"),
                   400: OpenApiResponse(description="Invalid CSV or validation errors")},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
