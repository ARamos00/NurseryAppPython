from __future__ import annotations

from typing import Any, Dict

from rest_framework import permissions, status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema

from core.utils.idempotency import idempotent
from nursery.imports import _open_csv, import_materials, import_plants, import_taxa


def _summary_payload(result) -> Dict[str, Any]:
    return {
        "rows_ok": result.rows_ok,
        "rows_failed": result.rows_failed,
        "errors": result.errors,
        "created_ids": result.created_ids,
    }


class BaseImportView(APIView):
    """
    Base for CSV import endpoints.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "imports"
    parser_classes = [MultiPartParser]  # expects multipart/form-data with a 'file' part

    def _dry_run(self, request: Request) -> bool:
        v = request.query_params.get("dry_run", "")
        return v in ("1", "true", "yes", "on", "True")

    def _get_file(self, request: Request):
        upload = request.FILES.get("file")
        if not upload:
            return None, Response({"file": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)
        return upload, None


class TaxaImportView(BaseImportView):
    @extend_schema(
        tags=["Imports"],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
                "required": ["file"],
            }
        },
        parameters=[
            OpenApiParameter(name="dry_run", type=OpenApiTypes.BOOL, location=OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Import summary JSON")},
        description="Import taxa via CSV with headers: scientific_name,cultivar,clone_code",
    )
    @idempotent
    def post(self, request: Request) -> Response:
        upload, err = self._get_file(request)
        if err:
            return err
        try:
            rows = list(_open_csv(upload))
        except ValueError as e:
            return Response({"file": [str(e)]}, status=status.HTTP_400_BAD_REQUEST)
        result = import_taxa(request.user, rows, dry_run=self._dry_run(request))
        return Response(_summary_payload(result))


class MaterialsImportView(BaseImportView):
    @extend_schema(
        tags=["Imports"],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
                "required": ["file"],
            }
        },
        parameters=[
            OpenApiParameter(name="dry_run", type=OpenApiTypes.BOOL, location=OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Import summary JSON")},
        description="Import materials via CSV with headers: taxon_id,material_type,lot_code,notes",
    )
    @idempotent
    def post(self, request: Request) -> Response:
        upload, err = self._get_file(request)
        if err:
            return err
        try:
            rows = list(_open_csv(upload))
        except ValueError as e:
            return Response({"file": [str(e)]}, status=status.HTTP_400_BAD_REQUEST)
        result = import_materials(request.user, rows, dry_run=self._dry_run(request))
        return Response(_summary_payload(result))


class PlantsImportView(BaseImportView):
    @extend_schema(
        tags=["Imports"],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
                "required": ["file"],
            }
        },
        parameters=[
            OpenApiParameter(name="dry_run", type=OpenApiTypes.BOOL, location=OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Import summary JSON")},
        description="Import plants via CSV with headers: taxon_id,batch_id,status,quantity,acquired_on,notes",
    )
    @idempotent
    def post(self, request: Request) -> Response:
        upload, err = self._get_file(request)
        if err:
            return err
        try:
            rows = list(_open_csv(upload))
        except ValueError as e:
            return Response({"file": [str(e)]}, status=status.HTTP_400_BAD_REQUEST)
        result = import_plants(request.user, rows, dry_run=self._dry_run(request))
        return Response(_summary_payload(result))
