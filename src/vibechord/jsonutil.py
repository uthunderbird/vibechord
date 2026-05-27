"""Small JSON conversion helpers."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, cast


def to_jsonable(value: object) -> object:
    """Convert dataclasses, tuples, and enums into JSON-compatible values."""

    if is_dataclass(value):
        return to_jsonable(asdict(cast(Any, value)))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [to_jsonable(item) for item in value]
    return value
