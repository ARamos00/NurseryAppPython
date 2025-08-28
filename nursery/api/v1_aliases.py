from __future__ import annotations

from rest_framework import serializers
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

# Canonical views
from accounts.views import CsrfView, LoginView, LogoutView, MeView, RegisterView
from nursery.exports import EventsExportView
from nursery.api.reports import InventoryReportView, ProductionReportView
from nursery.api.imports import TaxaImportView, MaterialsImportView, PlantsImportView
from nursery.serializers import EventSerializer


class ImportResultSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    updated = serializers.IntegerField(required=False)
    failed = serializers.IntegerField(required=False)
    errors = serializers.ListField(child=serializers.CharField(), required=False)


# ---- Auth v1 wrappers ---------------------------------------------------------
class CsrfV1View(CsrfView):
    @extend_schema(operation_id="auth_csrf_v1", summary="Prime CSRF cookie (v1)", responses={204: OpenApiResponse(description="CSRF cookie set")})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class LoginV1View(LoginView):
    @extend_schema(operation_id="auth_login_v1", summary="Log in (v1)")
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class LogoutV1View(LogoutView):
    @extend_schema(operation_id="auth_logout_v1", summary="Log out (v1)")
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class MeV1View(MeView):
    @extend_schema(operation_id="auth_me_v1", summary="Current user (v1)")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class RegisterV1View(RegisterView):
    @extend_schema(operation_id="auth_register_v1", summary="Register (v1)")
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


# ---- Exports / Reports / Imports (unchanged) ---------------------------------
class EventsExportV1View(EventsExportView):
    @extend_schema(
        operation_id="events_export_v1",
        summary="Events export (v1 mirror)",
        parameters=[OpenApiParameter(name="format", type=OpenApiTypes.STR, enum=["csv", "json"], location=OpenApiParameter.QUERY)],
        responses={(200, "text/csv"): OpenApiTypes.BINARY, (200, "application/json"): EventSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class InventoryReportV1View(InventoryReportView):
    @extend_schema(operation_id="report_inventory_v1", summary="Inventory report (v1 mirror)")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProductionReportV1View(ProductionReportView):
    @extend_schema(operation_id="report_production_v1", summary="Production report (v1 mirror)")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


_MULTIPART_FILE_REQUEST = {
    "multipart/form-data": {
        "type": "object",
        "properties": {"file": {"type": "string", "format": "binary", "description": "CSV file"}},
        "required": ["file"],
    }
}


class TaxaImportV1View(TaxaImportView):
    @extend_schema(operation_id="import_taxa_v1", summary="Taxa CSV import (v1)", request=_MULTIPART_FILE_REQUEST)
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class MaterialsImportV1View(MaterialsImportView):
    @extend_schema(operation_id="import_materials_v1", summary="Materials CSV import (v1)", request=_MULTIPART_FILE_REQUEST)
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class PlantsImportV1View(PlantsImportView):
    @extend_schema(operation_id="import_plants_v1", summary="Plants CSV import (v1)", request=_MULTIPART_FILE_REQUEST)
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
