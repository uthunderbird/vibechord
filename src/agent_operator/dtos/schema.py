from __future__ import annotations

from typing import Any, cast


def build_strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    sanitized = cast(dict[str, Any], _copy_json(schema))
    _strip_presentation_fields(sanitized)
    _normalize_strict_json_schema(sanitized)
    return sanitized


def _strip_presentation_fields(schema: dict[str, Any]) -> None:
    schema.pop("title", None)
    schema.pop("default", None)
    for key in ("$defs", "definitions"):
        nested_defs = schema.get(key)
        if isinstance(nested_defs, dict):
            for nested in nested_defs.values():
                if isinstance(nested, dict):
                    _strip_presentation_fields(nested)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for nested in properties.values():
            if isinstance(nested, dict):
                _strip_presentation_fields(nested)
    for key in ("anyOf", "oneOf", "allOf"):
        options = schema.get(key)
        if isinstance(options, list):
            for option in options:
                if isinstance(option, dict):
                    _strip_presentation_fields(option)
    items = schema.get("items")
    if isinstance(items, dict):
        _strip_presentation_fields(items)


def _normalize_strict_json_schema(schema: dict[str, Any]) -> None:
    schema_type = schema.get("type")
    properties = schema.get("properties")
    if schema_type == "object" and isinstance(properties, dict):
        schema["required"] = list(properties.keys())
        schema.setdefault("additionalProperties", False)
        for nested in properties.values():
            if isinstance(nested, dict):
                _normalize_strict_json_schema(nested)
    for key in ("$defs", "definitions"):
        nested_defs = schema.get(key)
        if isinstance(nested_defs, dict):
            for nested in nested_defs.values():
                if isinstance(nested, dict):
                    _normalize_strict_json_schema(nested)
    for key in ("anyOf", "oneOf", "allOf"):
        options = schema.get(key)
        if isinstance(options, list):
            for option in options:
                if isinstance(option, dict):
                    _normalize_strict_json_schema(option)
    items = schema.get("items")
    if isinstance(items, dict):
        _normalize_strict_json_schema(items)


def _copy_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_json(item) for item in value]
    return value
