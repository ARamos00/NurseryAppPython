from __future__ import annotations

from drf_spectacular.extensions import OpenApiSerializerFieldExtension
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    inline_serializer,
)
from rest_framework import serializers


# ------------------------------------------------------------------------------
# Shared components (headers, common error shapes) for reuse across endpoints
# ------------------------------------------------------------------------------

# Optimistic concurrency header
IF_MATCH_HEADER = OpenApiParameter(
    name="If-Match",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description=(
        "ETag of the resource obtained from the last GET. "
        "Required for PUT/PATCH/DELETE when concurrency enforcement is enabled."
    ),
)

# Idempotency header (safe retries of POST)
IDEMPOTENCY_KEY_HEADER = OpenApiParameter(
    name="Idempotency-Key",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "Client-provided key used to safely retry a POST. The first successful "
        "response for (user, method, path, body-hash) is replayed on duplicates."
    ),
)

# Owner QR endpoint uses a query token to prove possession of the raw token
LABEL_OWNER_QR_TOKEN_PARAM = OpenApiParameter(
    name="token",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
    required=True,
    description="Raw label token (proves possession) for the owner-only QR endpoint.",
)

# Common error payloads
ERROR_RESPONSE = OpenApiResponse(
    response=inline_serializer(
        name="Error",
        fields={
            "detail": serializers.CharField(),
            "code": serializers.CharField(required=False),
        },
    ),
    description="Error response",
)

VALIDATION_ERROR_RESPONSE = OpenApiResponse(
    response=inline_serializer(
        name="ValidationError",
        fields={
            # DRF default top-level error
            "detail": serializers.CharField(required=False),
            # Field or aggregate errors
            "errors": serializers.DictField(
                child=serializers.ListField(child=serializers.CharField()),
                required=False,
            ),
        },
    ),
    description="Validation error",
)

# Optional small examples (kept light and reusable)
IDEMPOTENCY_EXAMPLE = OpenApiExample(
    name="Idempotency Key",
    description="Send a unique key to make POST safe to retry.",
    value={"headers": {"Idempotency-Key": "c1e1c8bc-5cfe-4a76-9b6f-7a0b3e2d6b84"}},
)

IF_MATCH_EXAMPLE = OpenApiExample(
    name="If-Match",
    description="Use the ETag from the prior GET when updating/deleting.",
    value={"headers": {"If-Match": 'W/"Plant:42:1700000000"'}},
)


# ------------------------------------------------------------------------------
# Field extension for our custom LabelTargetField
# ------------------------------------------------------------------------------
class LabelTargetFieldExtension(OpenApiSerializerFieldExtension):
    """
    OpenAPI mapping for nursery.serializers.LabelTargetField:

      {
        "type": "plant" | "batch" | "material",
        "id":   <integer>
      }
    """
    target_class = "nursery.serializers.LabelTargetField"

    def map_serializer_field(self, auto_schema, direction):
        # Return a plain OpenAPI schema fragment (no side effects)
        return {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["plant", "batch", "material"]},
                "id": {"type": "integer", "minimum": 1},
            },
            "required": ["type", "id"],
            "additionalProperties": False,
        }
