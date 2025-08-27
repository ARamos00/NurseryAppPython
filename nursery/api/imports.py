from __future__ import annotations

"""
CSV import endpoints for taxa, materials, and plants.

Overview
--------
- Auth: `IsAuthenticated` (owner-scoped execution happens inside importer funcs).
- Throttle: `imports` scope guards upload frequency.
- Transport: `multipart/form-data` with a single `file` part (CSV).
- Idempotency: Each POST is decorated with `@idempotent`; the first successful
  response for `(user, key, method, path, body-hash)` is replayed on identical
  retries.
- Dry-run: `?dry_run=true|1|yes|on` validates and reports without persisting.
- Size limits: `_open_csv()` may raise `ValueError("File too large ...")`; we map
  those to HTTP 413 with a JSON error body.
- Error surface: Validation errors return a flat summary payload matching tests.

CSV contracts
-------------
- Taxa: headers `scientific_name,cultivar,clone_code`
- Materials: headers `taxon_id,material_type,lot_code,notes`
- Plants: headers `taxon_id,batch_id,status,quantity,acquired_on,notes`

Note:
    Actual parsing/validation is implemented in `nursery.imports` helpers.
"""

from typing import Any, Dict

from rest_framework import permissions, status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema  # noqa: E241

from core.utils.idempotency import idempotent
from nursery.imports import _open_csv, import_materials, import_plants, import_taxa
# Shared OpenAPI components
from nursery.schema import IDEMPOTENCY_KEY_HEADER, IDEMPOTENCY_EXAMPLE, VALIDATION_ERROR_RESPONSE, ERROR_RESPONSE


def _summary_payload(result) -> Dict[str, Any]:
    """Normalize importer result object into the API response contract."""
    return {
        "rows_ok": result.rows_ok,
        "rows_failed": result.rows_failed,
        "errors": result.errors,
        "created_ids": result.created_ids,
    }


class BaseImportView(APIView):
    """
    Base for CSV import endpoints.

    Behavior:
        - Requires authentication.
        - Applies `imports` throttle scope.
        - Expects `multipart/form-data` with a single `file` part.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "imports"
    parser_classes = [MultiPartParser]  # expects multipart/form-data with a 'file' part

    def _dry_run(self, request: Request) -> bool:
        """Return True when dry-run is requested via common truthy strings."""
        v = request.query_params.get("dry_run", "")
        return v in ("1", "true", "yes", "on", "True")

    def _get_file(self, request: Request):
        """
        Extract the uploaded file or return a DRF 400 Response if missing.

        Returns:
            (upload, None) on success, or (None, Response) on client error.

        WHY:
            Callers of this helper can simply `return err` when present, keeping
            flow straightforward without raising.
        """
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
            IDEMPOTENCY_KEY_HEADER,
        ],
        responses={
            200: OpenApiResponse(description="Import summary JSON"),
            400: VALIDATION_ERROR_RESPONSE,
            413: ERROR_RESPONSE,
        },
        examples=[IDEMPOTENCY_EXAMPLE],
        description="Import taxa via CSV with headers: scientific_name,cultivar,clone_code",
    )
    @idempotent
    def post(self, request: Request) -> Response:
        """Upload and process a taxa CSV; supports dry-run and idempotency."""
        upload, err = self._get_file(request)
        if err:
            return err
        try:
            rows = list(_open_csv(upload))
        except ValueError as e:
            # NOTE: `_open_csv` encodes size problems in the exception message.
            msg = str(e)
            status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if "File too large" in msg else status.HTTP_400_BAD_REQUEST
            return Response({"file": [msg]}, status=status_code)
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
            IDEMPOTENCY_KEY_HEADER,
        ],
        responses={
            200: OpenApiResponse(description="Import summary JSON"),
            400: VALIDATION_ERROR_RESPONSE,
            413: ERROR_RESPONSE,
        },
        examples=[IDEMPOTENCY_EXAMPLE],
        description="Import materials via CSV with headers: taxon_id,material_type,lot_code,notes",
    )
    @idempotent
    def post(self, request: Request) -> Response:
        """Upload and process a materials CSV; supports dry-run and idempotency."""
        upload, err = self._get_file(request)
        if err:
            return err
        try:
            rows = list(_open_csv(upload))
        except ValueError as e:
            msg = str(e)
            status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if "File too large" in msg else status.HTTP_400_BAD_REQUEST
            return Response({"file": [msg]}, status=status_code)
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
            IDEMPOTENCY_KEY_HEADER,
        ],
        responses={
            200: OpenApiResponse(description="Import summary JSON"),
            400: VALIDATION_ERROR_RESPONSE,
            413: ERROR_RESPONSE,
        },
        examples=[IDEMPOTENCY_EXAMPLE],
        description="Import plants via CSV with headers: taxon_id,batch_id,status,quantity,acquired_on,notes",
    )
    @idempotent
    def post(self, request: Request) -> Response:
        """Upload and process a plants CSV; supports dry-run and idempotency."""
        upload, err = self._get_file(request)
        if err:
            return err
        try:
            rows = list(_open_csv(upload))
        except ValueError as e:
            msg = str(e)
            status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if "File too large" in msg else status.HTTP_400_BAD_REQUEST
            return Response({"file": [msg]}, status=status_code)
        result = import_plants(request.user, rows, dry_run=self._dry_run(request))
        return Response(_summary_payload(result))
