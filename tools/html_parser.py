"""Helpers for pulling structured snippets out of saved HTML listings."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag


@dataclass(slots=True)
class AnchorBlock:
	"""Lightweight container for information harvested from an anchor."""

	url: str
	anchor_text: Optional[str] = None
	title: Optional[str] = None
	company: Optional[str] = None
	location: Optional[str] = None
	snippet: Optional[str] = None

	def to_dict(self) -> dict[str, str]:
		return {
			key: value
			for key, value in asdict(self).items()
			if value
		}


def extract_anchor_blocks(
	html: str,
	*,
	base_url: str | None = None,
	href_pattern: str | None = None,
	min_snippet_chars: int = 0,
	limit: int | None = None,
) -> List[AnchorBlock]:
	"""Parse the supplied HTML string and pull out anchor-centric snippets.

	Args:
		html: Raw HTML to parse.
		base_url: Optional base URL used to resolve relative link targets.
		href_pattern: Optional regular expression that href values must match.
		min_snippet_chars: Skip snippets shorter than this many characters.
		limit: Stop once this many blocks have been collected.

	Returns:
		A list of AnchorBlock instances ordered as they appear in the HTML.
	"""

	soup = BeautifulSoup(html, "html.parser")
	compiled_pattern = re.compile(href_pattern) if href_pattern else None

	results: List[AnchorBlock] = []
	seen_urls: set[str] = set()

	for anchor in soup.find_all("a", href=True):
		href = anchor.get("href", "").strip()
		if not href:
			continue

		if compiled_pattern and not compiled_pattern.search(href):
			continue

		absolute_url = urljoin(base_url or "", href)
		if absolute_url in seen_urls:
			continue

		container = _pick_container(anchor)
		snippet = _container_text(container)
		if min_snippet_chars and (not snippet or len(snippet) < min_snippet_chars):
			continue

		block = AnchorBlock(
			url=absolute_url,
			anchor_text=_safe_strip(anchor.get_text(" ")) or None,
			title=_extract_heading(container),
			company=_extract_company(container),
			location=_extract_location(container),
			snippet=snippet,
		)

		results.append(block)
		seen_urls.add(absolute_url)

		if limit is not None and len(results) >= limit:
			break

	return results


def _pick_container(node: Tag) -> Tag:
	"""Climb the DOM to find a container that likely represents a job card."""

	current = node
	for _ in range(6):
		if current.parent is None or not isinstance(current.parent, Tag):
			break

		parent: Tag = current.parent

		if parent.name in {"li", "article", "section"}:
			return parent

		if parent.name == "div":
			class_list = parent.get("class", [])
			if any("job" in c.lower() or "card" in c.lower() for c in class_list):
				return parent

			anchor_count = len(parent.find_all("a", href=True, recursive=False))
			if anchor_count > 1:
				return parent

		current = parent

	return node


def _container_text(container: Tag | None) -> Optional[str]:
	if container is None:
		return None

	text = " ".join(string.strip() for string in container.stripped_strings)
	return _safe_strip(text) or None


def _extract_heading(container: Tag | None) -> Optional[str]:
	if container is None:
		return None

	heading = container.find(["h1", "h2", "h3", "h4"])
	if heading:
		return _safe_strip(heading.get_text(" ")) or None

	return None


def _extract_company(container: Tag | None) -> Optional[str]:
	if container is None:
		return None

	icon = container.find("i", string=lambda value: value and "corporate_fare" in value)
	if icon and isinstance(icon.parent, Tag):
		return _safe_strip(" ".join(icon.parent.stripped_strings)) or None

	company_like = container.find(
		["span", "div"],
		attrs={"class": re.compile(r"company|employer|org", re.IGNORECASE)},
	)
	if company_like:
		return _safe_strip(company_like.get_text(" ")) or None

	return None


def _extract_location(container: Tag | None) -> Optional[str]:
	if container is None:
		return None

	icon = container.find("i", string=lambda value: value and "place" in value)
	if icon and isinstance(icon.parent, Tag):
		return _safe_strip(" ".join(icon.parent.stripped_strings)) or None

	location_like = container.find(
		["span", "div"],
		attrs={"class": re.compile(r"location|city|region", re.IGNORECASE)},
	)
	if location_like:
		return _safe_strip(location_like.get_text(" ")) or None

	return None


def _safe_strip(value: Optional[str]) -> Optional[str]:
	if not value:
		return None
	cleaned = re.sub(r"\s+", " ", value).strip()
	return cleaned or None


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="Extract anchor blocks from a saved HTML file and emit JSON.",
	)
	parser.add_argument("html_path", type=Path, help="Path to the saved HTML file")
	parser.add_argument("--base-url", help="Base URL used to resolve relative links")
	parser.add_argument(
		"--href-pattern",
		help="Only include anchors whose href matches this regular expression",
	)
	parser.add_argument(
		"--min-chars",
		type=int,
		default=0,
		help="Skip snippets shorter than this character count",
	)
	parser.add_argument(
		"--limit",
		type=int,
		help="Stop after emitting this many results",
	)
	parser.add_argument(
		"--pretty",
		action="store_true",
		help="Pretty-print JSON output for readability",
	)
	return parser


def main(argv: Optional[Iterable[str]] = None) -> None:
	args = _build_parser().parse_args(argv)

	html_path: Path = args.html_path
	if not html_path.exists():
		raise SystemExit(f"HTML file not found: {html_path}")

	html = html_path.read_text(encoding="utf-8", errors="ignore")
	blocks = extract_anchor_blocks(
		html,
		base_url=args.base_url,
		href_pattern=args.href_pattern,
		min_snippet_chars=args.min_chars,
		limit=args.limit,
	)

	payload = [block.to_dict() for block in blocks]
	json.dump(payload, sys.stdout, indent=2 if args.pretty else None)
	if args.pretty:
		sys.stdout.write("\n")


if __name__ == "__main__":
	main()
