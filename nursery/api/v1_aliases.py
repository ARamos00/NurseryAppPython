from __future__ import annotations

from rest_framework import serializers
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes

from nursery.exports import EventsExportView
from nursery.api.reports import InventoryReportView, ProductionReportView
from nursery.api.imports import TaxaImportView, MaterialsImportView, PlantsImportView
from nursery.serializers import EventSerializer


# ------------------------------------------------------------------------------
# Docs-only serializer for CSV import results.
# Adjust to match your real JSON envelope if it differs.
# ------------------------------------------------------------------------------
class ImportResultSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    updated = serializers.IntegerField(required=False)
    failed = serializers.IntegerField(required=False)
    errors = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Human-readable error messages per failed row.",
    )


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
        # Use tuple keys to specify media type for the same status code.
        # CSV is the default output; JSON is available for ?format=json.
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
    @extend_schema(
        operation_id="report_inventory_v1",
        summary="Inventory report (v1 mirror)",
        description="Mirror of /api/reports/inventory/ under /api/v1/.",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProductionReportV1View(ProductionReportView):
    @extend_schema(
        operation_id="report_production_v1",
        summary="Production report (v1 mirror)",
        description="Mirror of /api/reports/production/ under /api/v1/.",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# ------------------------------------------------------------------------------
# Imports (POST) — mirrors of /api/imports/*
# Document a multipart file upload and a simple JSON result.
# ------------------------------------------------------------------------------
_MULTIPART_FILE_REQUEST = {
    "multipart/form-data": {
        "type": "object",
        "properties": {
            # Swagger UI will render a file picker for this field.
            "file": {"type": "string", "format": "binary", "description": "CSV file"},
        },
        "required": ["file"],
    }
}


class TaxaImportV1View(TaxaImportView):
    @extend_schema(
        operation_id="import_taxa_v1",
        summary="Taxa CSV import (v1 mirror)",
        description="Upload a CSV with taxa. Field name: `file` (multipart/form-data).",
        request=_MULTIPART_FILE_REQUEST,
        responses={
            201: OpenApiResponse(response=ImportResultSerializer, description="Import result"),
            400: OpenApiResponse(description="Invalid CSV or validation errors"),
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class MaterialsImportV1View(MaterialsImportView):
    @extend_schema(
        operation_id="import_materials_v1",
        summary="Materials CSV import (v1 mirror)",
        description="Upload a CSV with plant materials. Field name: `file` (multipart/form-data).",
        request=_MULTIPART_FILE_REQUEST,
        responses={
            201: OpenApiResponse(response=ImportResultSerializer, description="Import result"),
            400: OpenApiResponse(description="Invalid CSV or validation errors"),
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class PlantsImportV1View(PlantsImportView):
    @extend_schema(
        operation_id="import_plants_v1",
        summary="Plants CSV import (v1 mirror)",
        description="Upload a CSV with plants. Field name: `file` (multipart/form-data).",
        request=_MULTIPART_FILE_REQUEST,
        responses={
            201: OpenApiResponse(response=ImportResultSerializer, description="Import result"),
            400: OpenApiResponse(description="Invalid CSV or validation errors"),
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
