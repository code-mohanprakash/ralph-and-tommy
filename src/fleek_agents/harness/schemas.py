"""Tool schemas for strict mode, made from the Pydantic models.

Strict mode makes the API guarantee the model's tool input matches the schema, but it only
accepts part of JSON Schema: no number limits, no length limits, no patterns. Those are dropped
from what's sent and still checked by Pydantic when the input comes back; a failure goes back to
the model as a correction. So the API guarantees the shape, and our code guarantees the rest.
"""

from typing import Any

from pydantic import BaseModel

UNSUPPORTED = {
    "title",
    "default",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
}


def _clean(node: Any) -> Any:
    if isinstance(node, list):
        return [_clean(item) for item in node]
    if not isinstance(node, dict):
        return node
    cleaned = {
        key: (value if key == "properties" else _clean(value))
        for key, value in node.items()
        if key not in UNSUPPORTED
    }
    if "properties" in cleaned:  # property names are data here, not schema keywords
        cleaned["properties"] = {name: _clean(sub) for name, sub in cleaned["properties"].items()}
    if cleaned.get("type") == "object":
        cleaned["additionalProperties"] = False
    return cleaned


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema: dict[str, Any] = _clean(model.model_json_schema())
    return schema
