"""Utility helpers for returning canned LLM responses during offline tests."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_LOCK_KEY_DEFAULT = "__list__"
_mock_cache: Optional[Dict[str, Any]] = None
_sequence_indices: Dict[Tuple[str, str], int] = {}


def mock_enabled() -> bool:
    """Return True when MOCK_LLM_RESPONSES points to a readable JSON file."""
    path = os.getenv("MOCK_LLM_RESPONSES")
    return bool(path and Path(path).exists())


def _load_cache() -> Dict[str, Any]:
    global _mock_cache
    if _mock_cache is not None:
        return _mock_cache
    path = os.getenv("MOCK_LLM_RESPONSES")
    if not path:
        _mock_cache = {}
        return _mock_cache
    file_path = Path(path)
    if not file_path.exists():
        _mock_cache = {}
        return _mock_cache
    _mock_cache = json.loads(file_path.read_text(encoding="utf-8"))
    return _mock_cache


def reset_mock_cache() -> None:
    """Force the cache to reload on next access (useful for tests)."""
    global _mock_cache
    _mock_cache = None
    _sequence_indices.clear()


def _next_from_sequence(bucket: str, key: str, values: Any) -> Any:
    sequence = values if isinstance(values, list) else [values]
    cursor_key = (bucket, key or _LOCK_KEY_DEFAULT)
    idx = _sequence_indices.get(cursor_key, 0)
    if idx >= len(sequence):
        idx = len(sequence) - 1
    _sequence_indices[cursor_key] = idx + 1
    return deepcopy(sequence[idx])


def get_mock_response(
    bucket: str | None,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    prompt: str | None = None,
) -> Any:
    """Return a canned response for the given bucket/metadata combination.

    Parameters
    ----------
    bucket: str | None
        Logical bucket name configured by the caller.
    metadata: dict | None
        Optional context (role name, job_url, iteration, etc.). Keys are matched
        against entries in the JSON payload.
    prompt: str | None
        Optional prompt string. Used only to ensure deterministic fallbacks
        (currently we just provide it for future debugging).
    """
    if not bucket or not mock_enabled():
        return None
    data = _load_cache()
    bucket_data = data.get(bucket)
    if bucket_data is None:
        return None

    if isinstance(bucket_data, list):
        return _next_from_sequence(bucket, _LOCK_KEY_DEFAULT, bucket_data)

    if isinstance(bucket_data, dict):
        # Try explicit metadata keys first.
        metadata = metadata or {}
        for key_name in ("job_url", "job_id", "role", "company", "field_id", "bucket_key"):
            meta_value = metadata.get(key_name)
            if meta_value and meta_value in bucket_data:
                return _next_from_sequence(bucket, str(meta_value), bucket_data[meta_value])
        # Fallback to default key.
        if "__default__" in bucket_data:
            return _next_from_sequence(bucket, "__default__", bucket_data["__default__"])
    # Primitive fallback (string/number)
    if isinstance(bucket_data, (str, int, float)):
        return bucket_data
    return None


__all__ = ["mock_enabled", "get_mock_response", "reset_mock_cache"]
