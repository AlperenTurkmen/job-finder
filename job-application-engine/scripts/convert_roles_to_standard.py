"""Convert raw role JSON files into the standard roles_parsed schema."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent
DEFAULT_SOURCE_DIR = REPO_ROOT / "data" / "roles"
DEFAULT_DEST_DIR = REPO_ROOT / "data" / "roles_parsed"

COUNTRY_ALIASES = {
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "england": "United Kingdom",
    "ireland": "Ireland",
    "cork, ireland": "Ireland",
    "schlieren": "Switzerland",
    "switzerland": "Switzerland",
    "germany": "Germany",
    "france": "France",
    "spain": "Spain",
    "italy": "Italy",
    "india": "India",
}


@dataclass
class ConversionStats:
    scanned: int = 0
    converted: int = 0
    skipped: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing raw role JSON files (default: data/roles)",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=DEFAULT_DEST_DIR,
        help="Directory where standard files will be written (default: data/roles_parsed)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without writing output files",
    )
    return parser.parse_args()


def slugify(*parts: str) -> str:
    text = "-".join(part for part in parts if part)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-")
    return text.lower() or "role"


def infer_country(location: str) -> str:
    if not location:
        return ""
    lowered = location.lower()
    for alias, canonical in COUNTRY_ALIASES.items():
        if alias in lowered:
            return canonical
    if "," in location:
        return location.split(",")[-1].strip()
    words = location.split()
    return words[-1] if words else ""


def ensure_list(value: object) -> List[str]:
    if isinstance(value, list):
        cleaned: List[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                cleaned.append(item.strip())
        return cleaned
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def safe_int(value: object, default: int = 5) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def ensure_skill_list(value: object) -> List[Dict[str, object]]:
    skills: List[Dict[str, object]] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                skills.append({"name": item.strip(), "importance": 5})
            elif isinstance(item, dict):
                name = item.get("name") or item.get("skill_name")
                if isinstance(name, str) and name.strip():
                    importance = safe_int(item.get("importance") or item.get("importance_score") or 5)
                    years = (
                        item.get("years_experience")
                        or item.get("years_experience_required")
                        or item.get("years_of_experience")
                    )
                    entry: Dict[str, object] = {"name": name.strip(), "importance": importance}
                    if isinstance(years, (int, float)):
                        entry["years_experience"] = years
                    skills.append(entry)
    return skills


def first_str(payload: Dict[str, object], keys: Iterable[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            list_value = next((item for item in value if isinstance(item, str) and item.strip()), None)
            if list_value:
                return list_value.strip()
    return ""


def numeric_from(payload: Dict[str, object], keys: Iterable[str]) -> int:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def convert_payload(payload: Dict[str, object], fallback_slug: str) -> Dict[str, object] | None:
    company = first_str(payload, ["company", "company_name", "employer", "org"])
    title = first_str(payload, ["role", "role_title", "job_title", "title"])
    location_value = payload.get("location") or payload.get("locations") or payload.get("city")
    if isinstance(location_value, list):
        location = next((item for item in location_value if isinstance(item, str) and item.strip()), "")
    else:
        location = location_value or ""

    if not company or not title:
        return None

    job_id = first_str(payload, ["job_id", "id", "slug"]) or slugify(company, title, location)

    responsibilities = ensure_list(
        payload.get("responsibilities")
        or payload.get("key_responsibilities")
        or payload.get("duties")
    )

    requirements = payload.get("requirements") if isinstance(payload.get("requirements"), dict) else {}
    must_have = ensure_list(
        payload.get("must_have_requirements") or requirements.get("must_have") or requirements.get("required")
    )
    nice_to_have = ensure_list(
        payload.get("nice_to_have_requirements")
        or requirements.get("nice_to_have")
        or requirements.get("preferred")
    )

    if not responsibilities:
        raw_text = payload.get("raw_text")
        if isinstance(raw_text, str) and raw_text.strip():
            responsibilities = [line.strip() for line in raw_text.split("\n") if line.strip()][:8]

    tech_stack = ensure_list(payload.get("tech_stack"))
    detected_stack = ensure_list(payload.get("tech_stack_detected"))
    for item in detected_stack:
        if item not in tech_stack:
            tech_stack.append(item)

    experience_summary = payload.get("experience_summary") if isinstance(payload.get("experience_summary"), dict) else {}
    exp_min = numeric_from(payload, ["experience_years_min", "min_years_experience", "minimum_years_experience"])
    exp_max = numeric_from(payload, ["experience_years_max", "max_years_experience", "maximum_years_experience"])
    if not exp_min:
        exp_min = numeric_from(experience_summary, [
            "minimum_years_experience",
            "minimum_total_experience",
            "software_development_years",
        ])
    if not exp_max:
        exp_max = numeric_from(experience_summary, [
            "maximum_years_experience",
            "maximum_total_experience",
            "software_development_years",
        ])
    skills = ensure_skill_list(payload.get("skills"))

    if not exp_max and exp_min:
        exp_max = exp_min

    standard = {
        "job_id": job_id,
        "company": company,
        "title": title,
        "location": location or "",
        "country": infer_country(location or ""),
        "seniority": first_str(payload, ["seniority", "level"]),
        "department": first_str(payload, ["department", "team", "org_unit"]),
        "employment_type": first_str(payload, ["employment_type", "job_type", "contract_type"]),
        "experience_years_min": exp_min,
        "experience_years_max": exp_max,
        "responsibilities": responsibilities,
        "must_have_requirements": must_have,
        "nice_to_have_requirements": nice_to_have,
        "skills": skills,
        "tech_stack": tech_stack,
        "min_years_experience": exp_min,
        "max_years_experience": exp_max,
        "raw_text": payload.get("raw_text", ""),
    }

    # Ensure at least empty lists for optional array fields
    for key in ["responsibilities", "must_have_requirements", "nice_to_have_requirements", "tech_stack"]:
        if not standard[key]:
            standard[key] = []

    return standard


def convert_directory(source_dir: Path, dest_dir: Path, dry_run: bool = False) -> ConversionStats:
    dest_dir.mkdir(parents=True, exist_ok=True)
    stats = ConversionStats()

    for json_file in sorted(source_dir.glob("*.json")):
        stats.scanned += 1
        try:
            payload = json.loads(json_file.read_text())
        except json.JSONDecodeError:
            stats.skipped += 1
            continue
        standard = convert_payload(payload, json_file.stem)
        if not standard:
            stats.skipped += 1
            continue
        stats.converted += 1
        if not dry_run:
            dest_path = dest_dir / json_file.name
            dest_path.write_text(json.dumps(standard, indent=2, ensure_ascii=False))

    return stats


def main() -> None:
    args = parse_args()
    stats = convert_directory(args.source_dir, args.dest_dir, dry_run=args.dry_run)
    print(
        json.dumps(
            {
                "scanned_files": stats.scanned,
                "converted": stats.converted,
                "skipped": stats.skipped,
                "dry_run": args.dry_run,
                "dest_dir": str(args.dest_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
