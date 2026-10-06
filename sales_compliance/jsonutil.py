"""Pull a JSON object out of model output."""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> dict:
    """Return the first JSON object in text. Tolerates code fences and leading prose."""
    cleaned = _FENCE.sub("", text.strip())
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output")
    obj, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    if not isinstance(obj, dict):
        raise ValueError("Model output JSON is not an object")
    return obj
