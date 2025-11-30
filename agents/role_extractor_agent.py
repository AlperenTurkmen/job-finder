"""LLM-assisted parser to normalize job roles from arbitrary JSON feeds."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Protocol

from agents.careers_page_finder_agent import GeminiClient


class LLMClient(Protocol):
    """Minimal interface describing the completion capability we need."""

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:  # pragma: no cover - protocol
        ...


PROMPT_TEMPLATE = """You are a structured data expert. You receive JSON captured from a company's careers feed.

Goals:
1. Inspect the JSON to find the array(s) that actually contain job postings.
2. Normalise each job posting into a consistent dictionary.
3. Every role MUST include a "title".
4. Include any other useful fields present (e.g. id, location, team, department, url, description, compensation).
5. If there are multiple potential arrays, prioritise the one that clearly represents individual job roles (for example, entries that have titles and identifiers).
6. Return JSON with the following structure:
   {{
     "roles": [
       {{
         "title": "...",
         "department": "...",
         "location": "...",
         "id": "...",
         "url": "...",
         "raw": {{ "optional": "copy of relevant source fields" }}
       }}
     ],
     "source_fields": ["JSON pointer style references to arrays you used"],
     "notes": "Optional clarifications or assumptions"
   }}

Rules:
- Always emit at least the title string for each role; omit entries that are clearly not jobs.
- Flatten arrays (join with commas) for fields like locations or teams.
- Preserve identifiers exactly as they appear.
- If you cannot find roles, return an empty list and explain why in "notes".
- Respond with valid JSON only, no prose outside the JSON.

Feed JSON (may be truncated):
{feed_json}

Respond with JSON only."""

MAX_PROMPT_CHARS = 12000


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _serialize_for_prompt(data: Any, *, limit: int = MAX_PROMPT_CHARS) -> str:
    try:
        payload = json.dumps(data, indent=2, ensure_ascii=False)
    except TypeError:
        payload = json.dumps(json.loads(json.dumps(data, default=str)), indent=2, ensure_ascii=False)
    if len(payload) <= limit:
        return payload
    return f"{payload[:limit]}\n... TRUNCATED ..."


def extract_roles_from_json(data: Any, llm: LLMClient) -> Dict[str, Any]:
    snippet = _serialize_for_prompt(data)
    prompt = PROMPT_TEMPLATE.format(feed_json=snippet)
    raw_response = llm.complete(prompt, temperature=0.0)
    cleaned = _strip_code_fence(raw_response)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:  # pragma: no cover - LLM failure
        raise ValueError(f"LLM returned invalid JSON: {cleaned}") from exc

    roles = parsed.get("roles")
    if roles is None or not isinstance(roles, list):
        raise ValueError("LLM response missing 'roles' list.")
    return parsed


def extract_roles_from_file(feed_path: Path, llm: LLMClient) -> Dict[str, Any]:
    data = json.loads(feed_path.read_text(encoding="utf-8"))
    return extract_roles_from_json(data, llm)


def extract_roles_with_gemini(feed_path: Path, model: str = "gemini-2.5-flash") -> Dict[str, Any]:
    client = GeminiClient(model=model)
    return extract_roles_from_file(feed_path, client)


__all__ = [
    "extract_roles_from_file",
    "extract_roles_from_json",
    "extract_roles_with_gemini",
]
