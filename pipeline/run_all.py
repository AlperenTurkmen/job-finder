
"""End-to-end pipeline: company name -> careers page -> job feed JSON."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from agents.careers_page_finder_agent import GeminiClient, choose_careers_page
from agents.role_extractor_agent import extract_roles_from_file
from tools.browser_capture import BrowserCaptureError, capture_feed_to_file
from tools.duckduckgo_search import duckduckgo_search
from tools.feed_discovery import FetchError, save_best_feed
from tools.google_search import google_search, print_search_results, write_results_json

DEFAULT_SEARCH_DIR = PROJECT_ROOT / "data" / "careers_pages"
DEFAULT_FEED_DIR = PROJECT_ROOT / "data" / "roles_raw"
DEFAULT_ROLES_DIR = PROJECT_ROOT / "data" / "roles_parsed"
DEFAULT_COMPANIES_FILE = PROJECT_ROOT / "data" / "companies" / "example_companies.csv"


def slugify(text: str) -> str:
	"""Convert arbitrary text into a filesystem-friendly slug."""

	slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
	return slug or "item"


def ensure_parent(path: Path) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)


def persist_search_results(results: list[dict], destination: Path) -> None:
	ensure_parent(destination)
	write_results_json(results, destination)
	print(f"[pipeline] saved search results to {destination}")


def _stringify_for_csv(value: object) -> str:
	if value is None:
		return ""
	if isinstance(value, str):
		return value
	if isinstance(value, (int, float)):
		return str(value)
	if isinstance(value, bool):
		return "true" if value else "false"
	return json.dumps(value, ensure_ascii=False)


def collect_role_rows(results: list[dict]) -> tuple[list[dict[str, str]], list[str]]:
	rows: list[dict[str, str]] = []
	fields: set[str] = {"company"}
	for result in results:
		company = result.get("company", "")
		roles = result.get("roles")
		if not isinstance(roles, list):
			continue
		for role in roles:
			if isinstance(role, dict):
				row = {"company": company}
				for key, value in role.items():
					row[key] = _stringify_for_csv(value)
				rows.append(row)
				fields.update(row.keys())
			else:
				rows.append({"company": company, "title": _stringify_for_csv(role)})
				fields.update({"company", "title"})

	if "title" not in fields:
		fields.add("title")

	ordered_fields = ["company", "title"]
	ordered_fields.extend(sorted(field for field in fields if field not in {"company", "title"}))
	return rows, ordered_fields


def write_roles_csv(results: list[dict], destination: Path) -> tuple[Path, int]:
	rows, fieldnames = collect_role_rows(results)
	ensure_parent(destination)
	with destination.open("w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=fieldnames)
		writer.writeheader()
		for row in rows:
			writer.writerow({field: row.get(field, "") for field in fieldnames})
	return destination, len(rows)


def run_pipeline(
	company: str,
	*,
	search_query: str,
	max_results: int,
	model: str,
	feed_debug: bool,
	headless_browser: str,
	headless_timeout: int,
	headless_wait: float,
	dump_all_json: bool,
	careers_url: str | None,
) -> dict:
	company_slug = slugify(company)
	search_path: Path | None = None
	llm = GeminiClient(model=model)
	search_provider = "manual" if careers_url else "google"

	if careers_url:
		print(f"[pipeline] skipping search, using supplied careers URL: {careers_url}")
		selection = {
			"chosen_url": careers_url,
			"confidence": "provided",
			"evidence": "URL passed via --careers-url",
		}
		chosen_url = careers_url
	else:
		print(f"[pipeline] searching for '{search_query}'")
		search_results: list[dict]
		try:
			search_results = google_search(search_query, max_results=max_results, debug=feed_debug)
			if not search_results:
				if feed_debug:
					print("[pipeline] google_search returned no results.")
				print("[pipeline] switching to DuckDuckGo search")
				search_provider = "duckduckgo"
				search_results = duckduckgo_search(search_query, max_results=max_results, debug=feed_debug)
		except requests.HTTPError as http_error:
			if feed_debug:
				print(f"[pipeline] google_search HTTPError: {http_error}")
			print("[pipeline] google search blocked; switching to DuckDuckGo")
			search_provider = "duckduckgo"
			search_results = duckduckgo_search(search_query, max_results=max_results, debug=feed_debug)
		except Exception as error:
			if feed_debug:
				print(f"[pipeline] google_search unexpected error: {error}")
			print("[pipeline] google search failed; switching to DuckDuckGo")
			search_provider = "duckduckgo"
			search_results = duckduckgo_search(search_query, max_results=max_results, debug=feed_debug)

		if not search_results:
			raise RuntimeError("Search step returned no organic results even after fallback.")

		print("[pipeline] top search results:")
		print_search_results(search_results[: min(5, len(search_results))])

		search_path = DEFAULT_SEARCH_DIR / f"{company_slug}.json"
		persist_search_results(search_results, search_path)

		selection = choose_careers_page(search_results, llm)
		print("[pipeline] LLM selection:")
		print(json.dumps(selection, indent=2, ensure_ascii=False))

		chosen_url = selection.get("chosen_url")
		if not chosen_url:
			raise RuntimeError("LLM did not return a 'chosen_url'.")

	feed_path = DEFAULT_FEED_DIR / f"{company_slug}.json"
	ensure_parent(feed_path)

	try:
		feed = save_best_feed(chosen_url, feed_path, debug=feed_debug)
		summary = {
			"source": "static",
			"feed_url": feed.url,
			"score": feed.score,
			"reason": feed.reason,
			"saved_to": str(feed_path),
		}
		print("[pipeline] static feed detection succeeded")
	except FetchError as exc:
		if feed_debug:
			print(f"[pipeline] static feed detection failed: {exc}")
		dump_dir = None
		if dump_all_json:
			dump_dir = DEFAULT_FEED_DIR / f"{company_slug}_captures"
		try:
			capture = capture_feed_to_file(
				chosen_url,
				feed_path,
				browser=headless_browser,
				timeout_ms=headless_timeout,
				wait_after_load=headless_wait,
				debug=feed_debug,
				dump_dir=dump_dir,
			)
		except BrowserCaptureError as browser_exc:
			raise RuntimeError(
				f"Headless browser capture failed: {browser_exc}"
			) from browser_exc

		summary = {
			"source": "headless",
			"feed_url": capture.feed.url,
			"score": capture.feed.score,
			"reason": capture.feed.reason,
			"saved_to": str(capture.saved_to),
		}
		if capture.captures_dir:
			summary["captures_dir"] = str(capture.captures_dir)
		print("[pipeline] headless browser capture succeeded")

	roles_output_path = DEFAULT_ROLES_DIR / f"{company_slug}.json"
	ensure_parent(roles_output_path)
	try:
		roles_payload = extract_roles_from_file(feed_path, llm)
	except Exception as exc:
		raise RuntimeError(f"Role extraction failed: {exc}") from exc
	roles = roles_payload.get("roles", []) if isinstance(roles_payload, dict) else []
	roles_json = json.dumps(roles_payload, indent=2, ensure_ascii=False)
	roles_output_path.write_text(roles_json, encoding="utf-8")
	print(f"[pipeline] extracted {len(roles)} role(s); saved to {roles_output_path}")
	if roles:
		print("[pipeline] roles:")
		for idx, role in enumerate(roles, start=1):
			title = str(role.get("title", "(missing title)") if isinstance(role, dict) else role)
			print(f"  {idx}. {title}")
			if isinstance(role, dict):
				for key, value in role.items():
					if key == "title" or value in (None, "", [], {}):
						continue
					if isinstance(value, (list, dict)):
						formatted = json.dumps(value, ensure_ascii=False)
					else:
						formatted = str(value)
					print(f"     {key}: {formatted}")

	result = {
		"company": company,
		"query": search_query,
		"selection": selection,
		"feed_summary": summary,
		"feed_path": str(feed_path),
		"roles_output_path": str(roles_output_path),
		"role_count": len(roles),
		"search_provider": search_provider,
	}
	if isinstance(roles_payload, dict):
		result["roles"] = roles
		if roles_payload.get("source_fields"):
			result["role_source_fields"] = roles_payload["source_fields"]
		if roles_payload.get("notes"):
			result["role_extraction_notes"] = roles_payload["notes"]
	if search_path:
		result["search_results_path"] = str(search_path)
	return result


def main() -> int:
	parser = argparse.ArgumentParser(
		description="Run the full careers discovery pipeline for one or more companies",
	)
	parser.add_argument("company", nargs="?", help="Company name to investigate")
	parser.add_argument(
		"--query",
		help="Override the search query (defaults to '<company> careers jobs')",
	)
	parser.add_argument(
		"--companies-file",
		help="Run the pipeline for every company listed in this text file (one per line)",
	)
	parser.add_argument("--max-results", type=int, default=10, help="Maximum search results to fetch")
	parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini model identifier")
	parser.add_argument("--feed-debug", action="store_true", help="Enable verbose feed detection logging")
	parser.add_argument(
		"--careers-url",
		help="Skip search/LLM and use this careers URL directly",
	)
	parser.add_argument(
		"--headless-browser",
		default="chromium",
		help="Playwright browser to use when static detection fails",
	)
	parser.add_argument(
		"--headless-timeout",
		type=int,
		default=30000,
		help="Navigation timeout in milliseconds for headless capture",
	)
	parser.add_argument(
		"--headless-wait",
		type=float,
		default=6.0,
		help="Seconds to wait after load before harvesting responses",
	)
	parser.add_argument(
		"--dump-all-json",
		action="store_true",
		help="When using headless capture, persist every JSON payload for inspection",
	)
	args = parser.parse_args()

	companies: list[str] = []
	manual_careers_urls: dict[str, str] = {}
	companies_file_input = args.companies_file
	if companies_file_input is None and not args.company:
		if DEFAULT_COMPANIES_FILE.exists():
			companies_file_input = str(DEFAULT_COMPANIES_FILE)
			print(f"[pipeline] using default companies file {DEFAULT_COMPANIES_FILE}")
		else:
			parser.error("Provide a company name or --companies-file (default companies file missing).")

	if companies_file_input:
		companies_path = Path(companies_file_input).expanduser()
		if not companies_path.exists():
			parser.error(f"Companies file not found: {companies_path}")
		lines = companies_path.read_text(encoding="utf-8").splitlines()
		for raw_line in lines:
			entry = raw_line.strip()
			if not entry:
				continue
			name = entry
			url: str | None = None
			for separator in ("|", ","):
				if separator in entry:
					name_part, url_part = entry.split(separator, 1)
					name = name_part.strip()
					url = url_part.strip() or None
					break
			if not name:
				continue
			companies.append(name)
			if url:
				manual_careers_urls[name] = url
	if args.company:
		companies.insert(0, args.company)
	if not companies:
		parser.error("Provide a company name or supply --companies-file.")
	if len(companies) > 1 and args.careers_url:
		parser.error("--careers-url can only be used when targeting a single company.")

	results: list[dict] = []
	failures: dict[str, str] = {}
	global_careers_url = args.careers_url if len(companies) == 1 else None
	for company in companies:
		search_query = args.query or f"{company} careers jobs"
		company_careers_url = manual_careers_urls.get(company) or global_careers_url
		try:
			result = run_pipeline(
				company,
				search_query=search_query,
				max_results=args.max_results,
				model=args.model,
				feed_debug=args.feed_debug,
				headless_browser=args.headless_browser,
				headless_timeout=args.headless_timeout,
				headless_wait=args.headless_wait,
				dump_all_json=args.dump_all_json,
				careers_url=company_careers_url,
			)
			results.append(result)
		except Exception as error:  # pragma: no cover - CLI entry point
			message = str(error)
			print(f"[pipeline] error for {company}: {message}")
			failures[company] = message

	if not results:
		print("[pipeline] all runs failed; no CSV generated.")
		return 1

	timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
	csv_path = DEFAULT_ROLES_DIR / f"run_{timestamp}.csv"
	csv_path, total_roles = write_roles_csv(results, csv_path)
	print(f"[pipeline] wrote consolidated roles CSV to {csv_path} ({total_roles} roles)")

	if len(results) == 1 and not args.companies_file:
		print("[pipeline] pipeline result:")
		print(json.dumps(results[0], indent=2, ensure_ascii=False))
	else:
		summary = {
			"successful_runs": len(results),
			"failed_runs": failures,
			"csv_path": str(csv_path),
			"total_roles": total_roles,
		}
		if companies_file_input:
			summary["companies_requested"] = companies
			if manual_careers_urls:
				summary["manual_careers_urls"] = manual_careers_urls
			if companies_file_input:
				summary["companies_file"] = str(Path(companies_file_input).expanduser())
		print("[pipeline] summary:")
		print(json.dumps(summary, indent=2, ensure_ascii=False))

	return 0 if not failures else 1


if __name__ == "__main__":
	raise SystemExit(main())
