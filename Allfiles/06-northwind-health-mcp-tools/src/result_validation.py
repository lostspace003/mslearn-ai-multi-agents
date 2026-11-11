from __future__ import annotations

from typing import Any

from jsonschema import ValidationError, validate


def validate_or_fallback(result: dict[str, Any], catalog_entry: dict[str, Any]) -> dict[str, Any]:
    """Return a validated tool result or the catalog's safe fallback."""
    # LAB PLACEHOLDER 6: Replace this line with the Task 6 sample.
    try:
        validate(instance=result, schema=catalog_entry["output_schema"])
    except ValidationError:
        return dict(catalog_entry["fallback"])
    return result