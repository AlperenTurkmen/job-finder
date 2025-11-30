"""Standalone Google search tool helper with structured output support."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Union

import requests


def _clean_heading(text: str) -> str:
    """Normalize the markdown heading returned by the proxy."""

    text = re.sub(r"!\[.*?\]\([^)]+\)", "", text)  # drop inline image references
    text = re.sub(r"\(blob:[^)]+\)", "", text)  # drop blob placeholders
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ·-*:")


def _clean_line(text: str) -> str:
    """Normalize supporting metadata lines."""

    text = re.sub(r"!\[.*?\]\([^)]+\)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ·-*:")


def google_search(
    query: str,
    max_results: int = 10,
    pause: float = 1.0,
    *,
    debug: bool = False,
) -> List[Dict[str, Union[str, int]]]:
    """Perform a Google search and return structured organic hits."""

    if debug:
        print(f"[google_search] received query='{query}' max_results={max_results}")
    del pause  # This tool routes through a static fetcher and needs no pacing.

    if not query.strip():
        raise ValueError("Search query cannot be empty.")

    proxy_url = "https://r.jina.ai/https://www.google.com/search"
    params = {"q": query, "num": max_results}
    if debug:
        print(f"[google_search] requesting {proxy_url} with params={params}")
    response = requests.get(proxy_url, params=params, timeout=20)
    if debug:
        print(f"[google_search] status_code={response.status_code}")
    response.raise_for_status()

    results: List[Dict[str, Union[str, int]]] = []
    seen_urls = set()
    match_pattern = re.compile(r"\[###\s*(.+?)\s*\]\((https?://[^\)]+)\)")
    lines = response.text.splitlines()
    total_lines = len(lines)
    line_idx = 0

    while line_idx < total_lines:
        line = lines[line_idx]
        match = match_pattern.search(line)
        if not match:
            line_idx += 1
            continue

        raw_title, href = match.groups()
        if debug:
            print(f"[google_search] line {line_idx + 1}: raw_title='{raw_title[:60]}' url='{href}'")
        if "google.com" in href and "url" in href:
            if debug:
                print("[google_search] skipped Google redirect")
            line_idx += 1
            continue
        if href in seen_urls:
            if debug:
                print("[google_search] skipped duplicate URL")
            line_idx += 1
            continue

        title = _clean_heading(raw_title)
        if not title:
            if debug:
                print("[google_search] skipped empty title after cleaning")
            line_idx += 1
            continue

        meta_lines: List[str] = []
        cursor = line_idx + 1
        while cursor < total_lines:
            candidate = lines[cursor].strip()
            if not candidate:
                cursor += 1
                break
            if candidate.startswith("###"):
                break
            if candidate.startswith("[###"):
                break
            meta_lines.append(candidate)
            cursor += 1

        source = None
        display_url = None
        snippet_parts: List[str] = []
        normalized_meta: List[str] = []
        for raw_meta in meta_lines:
            cleaned_meta = _clean_line(raw_meta)
            if not cleaned_meta:
                continue
            normalized_meta.append(cleaned_meta)
            lowered = cleaned_meta.lower()
            if source is None and not lowered.startswith("http") and "https://" not in lowered:
                source = cleaned_meta
                continue
            if display_url is None and ("https://" in cleaned_meta or "http://" in cleaned_meta or "›" in cleaned_meta):
                display_url = cleaned_meta
                continue
            snippet_parts.append(cleaned_meta)

        snippet = " ".join(snippet_parts).strip() or None

        result: Dict[str, Union[str, int, List[str]]] = {
            "rank": len(results) + 1,
            "title": title,
            "url": href,
            "raw_heading": raw_title.strip(),
        }
        if source:
            result["source"] = source
        if display_url:
            result["display_url"] = display_url
        if snippet:
            result["snippet"] = snippet
        if normalized_meta:
            result["metadata"] = normalized_meta

        results.append(result)
        seen_urls.add(href)
        if debug:
            print(f"[google_search] appended result #{result['rank']}: {title}")
        if len(results) >= max_results:
            if debug:
                print("[google_search] reached max_results")
            break

        line_idx = max(cursor, line_idx + 1)

    if debug:
        print(f"[google_search] collected {len(results)} results")
    return results


def print_search_results(results: List[Dict[str, Union[str, int, List[str]]]]) -> None:
    for item in results:
        rank_value = item.get("rank")
        rank = str(rank_value) if rank_value is not None else "-"
        print(f"{rank}. {item['title']}")
        print(f"   url: {item['url']}")
        if item.get("display_url"):
            print(f"   display: {item['display_url']}")
        if item.get("source"):
            print(f"   source: {item['source']}")
        if item.get("snippet"):
            print(f"   snippet: {item['snippet']}")


def write_results_json(results: List[Dict[str, Union[str, int, List[str]]]], destination: Path) -> None:
    payload = json.dumps(results, indent=2, ensure_ascii=False)
    destination.write_text(payload, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone Google Search helper")
    parser.add_argument("query", nargs="*", help="Search query to execute")
    parser.add_argument("--max-results", type=int, default=10, help="Maximum number of organic hits to return")
    parser.add_argument("--json-output", metavar="PATH", help="Write structured results to PATH (use '-' for stdout)")
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    query = " ".join(args.query) or "Greatest sports club in Turkey"
    if args.debug:
        print(f"[main] testing google_search with query: {query!r}")

    try:
        results = google_search(query, max_results=args.max_results, debug=args.debug)
    except Exception as error:
        print(f"[main] google_search raised: {error.__class__.__name__}: {error}")
        return 1

    if not results:
        print("[main] google_search returned no results")
        return 2

    if args.json_output:
        payload = json.dumps(results, indent=2, ensure_ascii=False)
        if args.json_output == "-":
            print(payload)
        else:
            path = Path(args.json_output).expanduser()
            write_results_json(results, path)
            if args.debug:
                print(f"[main] wrote JSON results to {path}")
        return 0

    print("[main] google_search returned results:")
    print_search_results(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
