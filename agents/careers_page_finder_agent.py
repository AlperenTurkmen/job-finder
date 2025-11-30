"""LLM-assisted selector that picks the best careers page from search results."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Protocol

import google.generativeai as genai

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from tools.browser_capture import BrowserCaptureError, capture_feed_to_file
from tools.feed_discovery import FetchError, save_best_feed


class LLMClient(Protocol):
	"""Simple interface describing the one method we need from any LLM client."""

	def complete(self, prompt: str, *, temperature: float = 0.0) -> str:  # pragma: no cover - interface only
		...


PROMPT_TEMPLATE = """You are an assistant helping me pick the correct careers page from Google search results.

Each result is a JSON object with fields such as "title", "url", "snippet", "source", "display_url", and "metadata".

Instructions:
1. Examine every result carefully.
2. Prefer URLs that are on the company's official domain and contain keywords like "careers", "jobs", "vacancies", "join-us", "work-with-us" or similar.
3. Avoid news articles, general information pages, third-party job boards, or social media unless no official page is available.
4. Return a JSON object with:
   - "chosen_url": the URL most likely leading to the official list of openings.
   - "confidence": high, medium, or low.
   - "evidence": One or two concise sentences citing the title/snippet/metadata that justify your choice.

Here are the search results as JSON:
{search_results}

Respond with only the JSON object specified above."""


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


def format_prompt(results: Iterable[Dict[str, Any]]) -> str:
	pretty_json = json.dumps(list(results), indent=2, ensure_ascii=False)
	return PROMPT_TEMPLATE.format(search_results=pretty_json)


def choose_careers_page(results: Iterable[Dict[str, Any]], llm: LLMClient) -> Dict[str, Any]:
	prompt = format_prompt(results)
	raw_response = llm.complete(prompt, temperature=0.0)
	cleaned = _strip_code_fence(raw_response)
	try:
		return json.loads(cleaned)
	except json.JSONDecodeError as exc:  # pragma: no cover - LLM failures
		raise ValueError(f"LLM returned invalid JSON: {cleaned}") from exc


def choose_from_file(results_path: Path, llm: LLMClient) -> Dict[str, Any]:
	data = json.loads(results_path.read_text(encoding="utf-8"))
	if not isinstance(data, list):
		raise ValueError("Expected a JSON array of search result objects")
	return choose_careers_page(data, llm)


class GeminiClient:
	"""Minimal wrapper around google.generativeai for this use case."""

	def __init__(self, model: str = "gemini-2.5-flash", api_key: str | None = None) -> None:
		self.model_name = model
		self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
		if not self.api_key:
			raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is not set.")
		genai.configure(api_key=self.api_key)
		self.model = genai.GenerativeModel(model)

	def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
		response = self.model.generate_content(
			prompt,
			generation_config={"temperature": temperature},
		)
		return (response.text or "").strip()


def choose_with_gemini(results_path: Path, model: str = "gemini-2.5-flash") -> Dict[str, Any]:
	client = GeminiClient(model=model)
	return choose_from_file(results_path, client)


def main() -> int:
	parser = argparse.ArgumentParser(description="Select the best careers page using Gemini 2.5 Flash")
	parser.add_argument("results_json", help="Path to the JSON file produced by the search step")
	parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini model to use")
	parser.add_argument(
		"--discover-feed",
		action="store_true",
		dest="discover_feed",
		help="Attempt to auto-detect the JSON feed powering the careers page and save it",
	)
	parser.add_argument(
		"--download-html",
		action="store_true",
		dest="discover_feed",
		help=argparse.SUPPRESS,
	)
	parser.add_argument(
		"--feed-debug",
		action="store_true",
		help="Print diagnostic information from the feed discovery step",
	)
	parser.add_argument(
		"--headless-browser",
		default="chromium",
		help="Playwright browser engine to use when falling back to headless capture",
	)
	parser.add_argument(
		"--headless-timeout",
		type=int,
		default=30000,
		help="Navigation timeout (ms) for headless capture",
	)
	parser.add_argument(
		"--headless-wait",
		type=float,
		default=6.0,
		help="Seconds to wait after initial load before collecting responses",
	)
	parser.add_argument(
		"--dump-all-json",
		action="store_true",
		help="When using the headless browser fallback, save every captured JSON response for inspection",
	)
	args = parser.parse_args()

	results_path = Path(args.results_json).expanduser()
	selection = choose_with_gemini(results_path, model=args.model)
	print(json.dumps(selection, indent=2, ensure_ascii=False))

	if args.discover_feed:
		chosen_url = selection.get("chosen_url")
		if not chosen_url:
			raise RuntimeError("LLM response missing 'chosen_url'; cannot detect job feed.")
		output_dir = Path("data") / "roles_raw"
		output_dir.mkdir(parents=True, exist_ok=True)
		slug = chosen_url.rstrip("/").split("/")[-1] or "careers"
		destination = output_dir / f"{slug}.json"
		dump_dir = None
		if args.dump_all_json:
			dump_dir = output_dir / f"{slug}_captures"

		try:
			feed = save_best_feed(
				chosen_url,
				destination,
				debug=args.feed_debug,
			)
			summary_payload = {
				"feed_url": feed.url,
				"score": feed.score,
				"reason": feed.reason,
				"saved_to": str(destination),
				"source": "static"
			}
		except FetchError as exc:
			if args.feed_debug:
				print(f"[feed-discovery] static detection failed: {exc}")
			try:
				capture = capture_feed_to_file(
					chosen_url,
					destination,
					browser=args.headless_browser,
					timeout_ms=args.headless_timeout,
					wait_after_load=args.headless_wait,
					debug=args.feed_debug,
					dump_dir=dump_dir,
				)
				summary_payload = {
					"feed_url": capture.feed.url,
					"score": capture.feed.score,
					"reason": capture.feed.reason,
					"saved_to": str(capture.saved_to),
					"source": "headless",
				}
				if capture.captures_dir:
					summary_payload["captures_dir"] = str(capture.captures_dir)
			except BrowserCaptureError as browser_exc:
				raise RuntimeError(
					f"Failed to auto-detect job feed using headless browser: {browser_exc}"
				) from browser_exc

		print(json.dumps(summary_payload, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
