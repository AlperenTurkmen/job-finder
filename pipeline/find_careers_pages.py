"""CLI helper to identify careers pages via Google search."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from tools.google_search import google_search, print_search_results, write_results_json

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "careers_pages"


def slugify(query: str) -> str:
	"""Convert a query string into a filesystem-friendly slug."""

	slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
	return slug or "search-results"


def resolve_output_path(query: str, override: str | None) -> Path:
	"""Determine where to store the structured search results."""

	if override:
		destination = Path(override).expanduser()
		if destination.is_dir():
			destination = destination / f"{slugify(query)}.json"
		return destination

	DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
	return DEFAULT_OUTPUT_DIR / f"{slugify(query)}.json"


def main() -> int:
	parser = argparse.ArgumentParser(description="Find likely careers pages for a company query")
	parser.add_argument("query", nargs="*", help="Search query describing the target company and vacancies")
	parser.add_argument("--max-results", type=int, default=10, help="Maximum number of organic results to inspect")
	parser.add_argument("--json-output", metavar="PATH", help="Write structured JSON to PATH (directory or file). Use '-' for stdout.")
	parser.add_argument("--debug", action="store_true", help="Enable verbose logging from the search helper")
	args = parser.parse_args()

	query_parts: List[str] = args.query or []
	query = " ".join(query_parts).strip()
	if not query:
		parser.error("Please provide a search query, e.g. python pipeline/find_careers_pages.py 'Rockstar vacancies UK'")

	results = google_search(query, max_results=args.max_results, debug=args.debug)
	if not results:
		print("No organic results detected for that query.")
		return 2

	print_search_results(results)

	if args.json_output == "-":
		payload = json.dumps(results, indent=2, ensure_ascii=False)
		print(payload)
		return 0

	destination = resolve_output_path(query, args.json_output)
	destination.parent.mkdir(parents=True, exist_ok=True)
	write_results_json(results, destination)
	print(f"Saved structured results to {destination}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
