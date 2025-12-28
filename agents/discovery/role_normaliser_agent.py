"""LLM agent that converts raw role descriptions into structured JSON files.

The agent expects CSV input with a ``raw_text`` column, calls an LLM with a
customisable prompt template, and writes the structured roles to disk using the
schema consumed by downstream pipelines.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Protocol

from dotenv import load_dotenv

# Load environment variables
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

from agents.discovery.careers_page_finder_agent import GeminiClient


class LLMClient(Protocol):
    """Minimal interface describing the completion capability we need."""

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:  # pragma: no cover - protocol
        ...


@dataclass(slots=True)
class ConversionResult:
    """Bookkeeping for a single conversion run."""

    index: int
    prompt: str
    output_path: Path
    payload: Dict[str, Any]
    status: str


DEFAULT_PROMPT = """You are a job role normalisation agent.

Your task is to convert any job posting into structured JSON that follows the
schema exactly. Use UK English spelling throughout.

Return only valid JSON. Do not add commentary. If a field is missing from the
source text, supply an appropriate empty value ([], null, or 0).

Required schema example:
{example_json}

Extraction rules:
1. Seniority
    - Infer from wording:
    - "junior" -> Junior
    - "mid-level", "II", "2" -> Mid-level
    - "senior", "lead", "principal" -> Senior
2. Responsibilities
    - Capture explicit or implied duties as concise action-led bullet points.
3. Must-have vs nice-to-have requirements
    - Must-have cues: "required", "must", "minimum", "at least", "strong experience".
    - Nice-to-have cues: "bonus", "nice to have", "preferably", "helpful", "preferred", "advantage".
4. Skills extraction
    - Include technologies, programming languages, frameworks, cloud platforms,
      tooling, operating systems, methodologies, and notable soft skills.
        - Normalise naming (for example "python3" -> "Python").
5. Importance scoring (0–10)
    - 10: essential core skill.
    - 7–9: strongly emphasised.
    - 4–6: useful but optional.
    - 1–3: minor mention.
    - 0: irrelevant.
6. Years of experience estimation
         - Use stated numbers where provided ("3+ years" -> 3).
         - Interpret phrases: "strong experience" -> 3, "working knowledge" -> 1,
             "familiarity" or "exposure" -> 0.
7. Tech stack detected
         - Deduplicate key technologies and keep the list concise (for example "Python",
             "Kotlin", "AWS", "PostgreSQL").
8. Experience summary
    - Populate fields when the description provides explicit minimum experience.
      Otherwise leave values at 0.
9. ID generation
        - If not supplied, construct "{{company}}_{{role}}_{{location}}" in lowercase with
      words separated by underscores.
10. Raw text
    - Insert the full, unedited job description.

Job posting:
{raw_text}
"""


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


def _slugify(value: str, *, fallback: str) -> str:
    """Generate a filesystem-friendly slug."""

    value = value.strip().lower()
    if not value:
        return fallback
    slug = re.sub(r"[^a-z0-9]+", "-", value)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or fallback


def _format_prompt(template: str, raw_text: str, example_json: str | None) -> str:
    if not raw_text.strip():
        raise ValueError("raw_text is empty after stripping whitespace")
    example_section = example_json or ""
    return template.format(raw_text=raw_text.strip(), example_json=example_section)


def _ensure_prompt_placeholders(template: str) -> None:
    # Fail fast if the caller forgot placeholders.
    try:
        template.format(raw_text="sample text", example_json="sample json")
    except (KeyError, IndexError):  # pragma: no cover - defensive programming
        raise ValueError("Prompt template must contain named placeholders 'raw_text' and 'example_json'.")


def convert_raw_text(
    raw_text: str,
    *,
    llm: LLMClient,
    prompt_template: str,
    example_json: str | None = None,
    temperature: float = 0.0,
) -> tuple[Dict[str, Any], str]:
    """Convert a single raw job description into structured JSON."""

    prompt = _format_prompt(prompt_template, raw_text, example_json)
    raw_response = llm.complete(prompt, temperature=temperature)
    cleaned = _strip_code_fence(raw_response)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:  # pragma: no cover - LLM failure
        raise ValueError(f"LLM returned invalid JSON: {cleaned}") from exc
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    return payload, prompt


def _build_filename(payload: Dict[str, Any], *, index: int) -> str:
    # Prefer explicit identifiers, otherwise fall back to a slug derived from company/title.
    if isinstance(payload.get("id"), str) and payload["id"].strip():
        return f"{_slugify(payload['id'], fallback=f'role-{index:02d}')}.json"

    company = payload.get("company_name") if isinstance(payload.get("company_name"), str) else ""
    title = payload.get("role_title") if isinstance(payload.get("role_title"), str) else ""
    composite = " ".join(part for part in (company, title) if part)
    if composite:
        return f"{_slugify(composite, fallback=f'role-{index:02d}')}.json"
    return f"role-{index:02d}.json"


def _iter_csv_rows(csv_path: Path) -> Iterable[str]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "raw_text" not in (reader.fieldnames or []):
            raise ValueError("CSV file must contain a 'raw_text' column")
        for row in reader:
            yield row.get("raw_text", "")


def _index_existing_roles(output_dir: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    by_id: dict[str, Path] = {}
    by_name: dict[str, Path] = {}
    if not output_dir.exists():
        return by_id, by_name
    for path in output_dir.glob("*.json"):
        by_name[path.name] = path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        role_id = data.get("id")
        if isinstance(role_id, str) and role_id.strip():
            by_id[role_id.strip()] = path
    return by_id, by_name


def convert_roles_csv(
    csv_path: Path,
    *,
    llm: LLMClient,
    prompt_template: str = DEFAULT_PROMPT,
    example_json: str | None = None,
    output_dir: Path,
    temperature: float = 0.0,
    max_rows: int | None = None,
    overwrite: bool = False,
) -> List[ConversionResult]:
    """Process all rows in the CSV and write structured role JSON files."""

    _ensure_prompt_placeholders(prompt_template)
    output_dir.mkdir(parents=True, exist_ok=True)
    existing_by_id, existing_by_name = _index_existing_roles(output_dir)

    results: List[ConversionResult] = []
    for index, raw_text in enumerate(_iter_csv_rows(csv_path), start=1):
        if max_rows is not None and len(results) >= max_rows:
            break
        if not raw_text.strip():
            continue
        payload, prompt = convert_raw_text(
            raw_text,
            llm=llm,
            prompt_template=prompt_template,
            example_json=example_json,
            temperature=temperature,
        )
        role_id = payload.get("id") if isinstance(payload.get("id"), str) else ""
        destination = None

        if role_id:
            destination = existing_by_id.get(role_id.strip())

        filename = _build_filename(payload, index=index)
        destination = destination or existing_by_name.get(filename) or (output_dir / filename)

        existing_payload: Dict[str, Any] | None = None
        if destination.exists():
            try:
                existing_payload = json.loads(destination.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing_payload = None

        status = "created"
        should_write = True

        if existing_payload is not None:
            if existing_payload == payload:
                status = "unchanged"
                should_write = False
            elif overwrite:
                status = "updated"
                should_write = True
            else:
                status = "skipped"
                should_write = False

        if should_write:
            destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            existing_by_name[destination.name] = destination
            if role_id:
                existing_by_id[role_id.strip()] = destination

        results.append(
            ConversionResult(
                index=index,
                prompt=prompt,
                output_path=destination,
                payload=payload,
                status=status,
            )
        )
    return results


def _load_text(path: Path | None) -> str | None:
    if not path:
        return None
    if not path.exists():
        print(f"[role-normaliser] auxiliary file not found: {path}. Continuing without it.", file=sys.stderr)
        return None
    return path.read_text(encoding="utf-8").strip() or None


def run_agent(
    csv_path: Path,
    *,
    prompt_path: Path | None,
    example_path: Path | None,
    output_dir: Path,
    model: str,
    temperature: float,
    max_rows: int | None,
    overwrite: bool,
) -> List[ConversionResult]:
    prompt_template = _load_text(prompt_path) or DEFAULT_PROMPT
    example_json = _load_text(example_path)
    llm = GeminiClient(model=model)
    return convert_roles_csv(
        csv_path,
        llm=llm,
        prompt_template=prompt_template,
        example_json=example_json,
        output_dir=output_dir,
        temperature=temperature,
        max_rows=max_rows,
        overwrite=overwrite,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert raw role descriptions to structured JSON using an LLM")
    parser.add_argument("csv_path", type=Path, help="Path to the CSV file containing a 'raw_text' column")
    parser.add_argument("--prompt-file", dest="prompt_path", type=Path, help="Path to a prompt template file")
    parser.add_argument(
        "--example-json",
        dest="example_path",
        type=Path,
        help="Path to a JSON file used as an in-prompt example",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        type=Path,
        default=Path("data") / "roles",
        help="Directory where structured JSON files will be written",
    )
    parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini model to use")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature for the LLM")
    parser.add_argument("--max-rows", type=int, help="Limit the number of rows processed from the CSV")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing JSON files if they already exist",
    )
    args = parser.parse_args()

    results = run_agent(
        args.csv_path,
        prompt_path=args.prompt_path,
        example_path=args.example_path,
        output_dir=args.output_dir,
        model=args.model,
        temperature=args.temperature,
        max_rows=args.max_rows,
        overwrite=args.overwrite,
    )

    for result in results:
        print(result.output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ConversionResult",
    "DEFAULT_PROMPT",
    "convert_raw_text",
    "convert_roles_csv",
    "run_agent",
]
