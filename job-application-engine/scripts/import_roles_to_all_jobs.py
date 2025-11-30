"""Merge parsed role JSON files into the ADK all_jobs.json payload."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent
DEFAULT_ROLES_DIR = REPO_ROOT / "data" / "roles"
DEFAULT_ALL_JOBS = APP_DIR / "input" / "all_jobs.json"


@dataclass
class MergeStats:
    scanned: int = 0
    converted: int = 0
    skipped_missing_fields: int = 0
    duplicates: int = 0
    written: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roles-dir",
        type=Path,
        default=DEFAULT_ROLES_DIR,
        help="Directory containing role JSON files (default: data/roles_parsed)",
    )
    parser.add_argument(
        "--all-jobs-file",
        type=Path,
        default=DEFAULT_ALL_JOBS,
        help="Target JSON file to update (default: job-application-engine/input/all_jobs.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report without modifying all_jobs.json",
    )
    parser.add_argument(
        "--keep-duplicates",
        action="store_true",
        help="Append every role even if company/role/location match an existing entry",
    )
    return parser.parse_args()


def load_existing(all_jobs_path: Path) -> Tuple[List[Dict[str, object]], set[Tuple[str, str, str]]]:
    if not all_jobs_path.exists():
        all_jobs_path.parent.mkdir(parents=True, exist_ok=True)
        return [], set()
    data = json.loads(all_jobs_path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"Expected {all_jobs_path} to contain a JSON array")
    keys = {canonical_key(entry) for entry in data if isinstance(entry, dict)}
    return data, keys


def canonical_key(entry: Dict[str, object]) -> Tuple[str, str, str]:
    company = str(entry.get("company", "")).strip().lower()
    role = str(entry.get("role", "")).strip().lower()
    location = str(entry.get("location", "")).strip().lower()
    return (company, role, location)


def collect_role_files(roles_dir: Path) -> Sequence[Path]:
    if not roles_dir.exists():
        raise FileNotFoundError(f"Roles directory not found: {roles_dir}")
    return sorted(path for path in roles_dir.glob("*.json") if path.is_file())


def build_entry(payload: Dict[str, object]) -> Dict[str, object] | None:
    company = _first_str(payload, ["company", "company_name", "employer", "org"])
    role = _first_str(payload, ["role", "role_title", "title", "job_title"])
    location = _first_str(payload, ["location", "locations", "city", "country"])
    if not company or not role:
        return None

    entry = {
        "company": company,
        "role": role,
        "location": location or "",
    "salary": _first_str(payload, ["salary", "salary_range", "compensation", "pay_range"]),
    "job_type": _first_str(payload, ["employment_type", "job_type", "contract_type"]),
        "tech_stack": _extract_list(payload.get("tech_stack")) or _extract_skill_names(payload.get("skills")),
        "responsibilities": _extract_list(payload.get("responsibilities"))
        or _extract_list(payload.get("must_have_requirements"))
        or _extract_list(payload.get("nice_to_have_requirements")),
    }
    raw_text = payload.get("raw_text")
    if not entry["responsibilities"] and isinstance(raw_text, str) and raw_text.strip():
        entry["responsibilities"] = _split_raw_text(raw_text)
    return entry


def _first_str(payload: Dict[str, object], keys: Iterable[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return ""


def _extract_list(value: object) -> List[str]:
    if isinstance(value, list):
        cleaned: List[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                cleaned.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("text") or item.get("value") or item.get("description")
                if isinstance(text, str) and text.strip():
                    cleaned.append(text.strip())
        return cleaned
    return []


def _extract_skill_names(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return names


def _split_raw_text(raw_text: str, max_items: int = 5) -> List[str]:
    parts = [segment.strip() for segment in raw_text.split("\n") if segment.strip()]
    return parts[:max_items]


def merge_roles(
    roles_dir: Path,
    all_jobs_path: Path,
    dry_run: bool = False,
    keep_duplicates: bool = False,
) -> MergeStats:
    stats = MergeStats()
    existing, keys = load_existing(all_jobs_path)
    new_entries: List[Dict[str, object]] = []

    for role_file in collect_role_files(roles_dir):
        stats.scanned += 1
        try:
            payload = json.loads(role_file.read_text())
        except json.JSONDecodeError:
            stats.skipped_missing_fields += 1
            continue
        entry = build_entry(payload)
        if not entry:
            stats.skipped_missing_fields += 1
            continue
        key = canonical_key(entry)
        if not keep_duplicates:
            if key in keys:
                stats.duplicates += 1
                continue
            keys.add(key)
        else:
            stats.duplicates += 1 if key in keys else 0
        new_entries.append(entry)
        stats.converted += 1

    if not dry_run and new_entries:
        existing.extend(new_entries)
        all_jobs_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
        stats.written = len(new_entries)

    return stats


def main() -> None:
    args = parse_args()
    stats = merge_roles(
        args.roles_dir,
        args.all_jobs_file,
        dry_run=args.dry_run,
        keep_duplicates=args.keep_duplicates,
    )
    print(
        json.dumps(
            {
                "scanned_files": stats.scanned,
                "converted": stats.converted,
                "duplicates": stats.duplicates,
                "skipped": stats.skipped_missing_fields,
                "written": stats.written,
                "dry_run": args.dry_run,
                "keep_duplicates": args.keep_duplicates,
                "all_jobs_file": str(args.all_jobs_file),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
