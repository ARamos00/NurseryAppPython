from __future__ import annotations

from drf_spectacular.extensions import OpenApiSerializerFieldExtension


class LabelTargetFieldExtension(OpenApiSerializerFieldExtension):
    """
    OpenAPI mapping for nursery.serializers.LabelTargetField.

    Represents a small object:
      {
        "type": "plant" | "batch" | "material",
        "id":   <integer>
      }
    """
    target_class = "nursery.serializers.LabelTargetField"

    def map_serializer_field(self, auto_schema, direction):
        # Return a plain OpenAPI schema fragment
        return {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["plant", "batch", "material"]},
                "id": {"type": "integer", "minimum": 1},
            },
            "required": ["type", "id"],
            "additionalProperties": False,
        }
