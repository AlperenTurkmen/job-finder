"""DuckDuckGo search helper returning structured organic results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Union

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def duckduckgo_search(
    query: str,
    max_results: int = 10,
    *,
    debug: bool = False,
) -> List[Dict[str, Union[str, int]]]:
    """Perform a DuckDuckGo query and return structured results.

    Falls back to a minimal set of fields compatible with google_search results.
    """

    if not query.strip():
        raise ValueError("Search query cannot be empty.")

    params = {"q": query}
    response = requests.get(
        "https://duckduckgo.com/html/",
        params=params,
        headers=_HEADERS,
        timeout=20,
    )
    if debug:
        print(f"[duckduckgo_search] status_code={response.status_code} for query={query!r}")
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results: List[Dict[str, Union[str, int]]] = []
    seen_urls = set()

    for block in soup.select("div.result"):
        anchor = block.select_one("a.result__a")
        if not anchor:
            continue

        href = anchor.get("href")
        if not href or href.startswith("/"):
            continue
        if href in seen_urls:
            continue

        title = anchor.get_text(" ", strip=True)
        if not title:
            continue

        snippet_el = block.select_one("div.result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else None
        display_url_el = block.select_one("span.result__url")
        display_url = display_url_el.get_text(" ", strip=True) if display_url_el else None

        result: Dict[str, Union[str, int]] = {
            "rank": len(results) + 1,
            "title": title,
            "url": href,
            "source": "DuckDuckGo",
        }
        if display_url:
            result["display_url"] = display_url
        if snippet:
            result["snippet"] = snippet

        results.append(result)
        seen_urls.add(href)
        if len(results) >= max_results:
            break

    if debug:
        print(f"[duckduckgo_search] collected {len(results)} results")
    return results


def main() -> int:  # pragma: no cover - convenience CLI
    import argparse

    parser = argparse.ArgumentParser(description="DuckDuckGo search helper")
    parser.add_argument("query", nargs="*", help="Search query to execute")
    parser.add_argument("--max-results", type=int, default=10, help="Maximum results to return")
    parser.add_argument("--json-output", metavar="PATH", help="Write structured results to PATH (use '-' for stdout)")
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    query = " ".join(args.query) or "OpenAI careers"
    try:
        results = duckduckgo_search(query, max_results=args.max_results, debug=args.debug)
    except Exception as error:
        print(f"duckduckgo_search error: {error}")
        return 1

    if args.json_output:
        payload = json.dumps(results, indent=2, ensure_ascii=False)
        if args.json_output == "-":
            print(payload)
        else:
            path = Path(args.json_output).expanduser()
            path.write_text(payload, encoding="utf-8")
            if args.debug:
                print(f"Wrote results to {path}")
        return 0

    for item in results:
        rank = item.get("rank", "-")
        print(f"{rank}. {item['title']}")
        print(f"   url: {item['url']}")
        if item.get("display_url"):
            print(f"   display: {item['display_url']}")
        if item.get("snippet"):
            print(f"   snippet: {item['snippet']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
