from __future__ import annotations

import os
import time
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ValidationError


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        tmp_path.write_text(content, encoding=encoding)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def read_text_with_retry(
    path: Path,
    *,
    attempts: int = 5,
    delay_seconds: float = 0.02,
    encoding: str = "utf-8",
) -> str:
    last_payload = ""
    for index in range(attempts):
        payload = path.read_text(encoding=encoding)
        if payload.strip():
            return payload
        last_payload = payload
        if index < attempts - 1:
            time.sleep(delay_seconds)
    return last_payload


def model_validate_json_file_with_retry[ModelT: BaseModel](
    model_type: type[ModelT],
    path: Path,
    *,
    attempts: int = 5,
    delay_seconds: float = 0.02,
    encoding: str = "utf-8",
) -> ModelT:
    last_error: ValidationError | None = None
    for index in range(attempts):
        payload = read_text_with_retry(
            path,
            attempts=1,
            delay_seconds=delay_seconds,
            encoding=encoding,
        )
        try:
            return model_type.model_validate_json(payload)
        except ValidationError as exc:
            last_error = exc
            if index < attempts - 1:
                time.sleep(delay_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Failed to load JSON model from {path}")
