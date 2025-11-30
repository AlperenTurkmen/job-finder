"""Heuristic discovery of job listing feeds hidden behind dynamic career pages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urljoin

import requests

from .fetcher import FetchError, fetch_html

URL_PATTERN = re.compile(r'["\'`](https?:\/\/[^"\'`<>]+|\/[^"\'`<>]+)["\'`]', re.IGNORECASE)
KEYWORDS = (
	"job",
	"career",
	"position",
	"opening",
	"vacancy",
	"role",
	"listing",
	"opportunity",
)

PRIMARY_JOB_KEYWORDS = (
	"job",
	"jobs",
	"position",
	"positions",
	"career",
	"careers",
	"opening",
	"openings",
	"vacanc",
	"role",
	"roles",
	"posting",
	"reqid",
)

SECONDARY_JOB_KEYWORDS = (
	"title",
	"jobtitle",
	"department",
	"team",
	"category",
	"company",
	"location",
	"city",
	"country",
	"req",
	"apply",
)

NEGATIVE_KEYWORDS = (
	"cookie",
	"optanon",
	"onetrust",
	"consent",
	"analytics",
	"gtm",
	"tracking",
)

PRIMARY_TEXT_TOKENS = (
	"jobspositionlist",
	"jobsposition",
	"jobsposting",
	"jobscategory",
	"jobsite",
	"jobscount",
)

DEFAULT_TIMEOUT = 20
MAX_SCRIPT_BYTES = 200_000
MAX_SCRIPT_FETCHES = 6
MAX_ENDPOINT_TRIES = 30
MAX_INLINE_NODE_VISITS = 2000
MAX_INLINE_DEPTH = 6
MAX_INLINE_LIST_SAMPLES = 8

INLINE_JSON_PATTERNS = (
	(
		"staticRouterHydrationData",
		re.compile(
			r"window\.__staticRouterHydrationData\s*=\s*JSON\.parse\(\"(.*?)\"\);",
			re.DOTALL,
		),
		"json_parse",
	),
	(
		"__NUXT__",
		re.compile(r"window\.__NUXT__\s*=\s*(\{.*?\});", re.DOTALL),
		"raw_json",
	),
	(
		"__NEXT_DATA__",
		re.compile(
			r"<script[^>]+id=\"__NEXT_DATA__\"[^>]*>(\{.*?\})</script>",
			re.DOTALL,
		),
		"raw_json",
	),
)

INLINE_LIST_KEYS = (
	"items",
	"results",
	"jobs",
	"roles",
	"positions",
	"openings",
	"list",
	"data",
	"searchResults",
	"opportunities",
)


@dataclass(slots=True)
class FeedCandidate:
	url: str
	score: float
	reason: str
	payload: object
	content_type: str
	status_code: int


@dataclass(slots=True)
class PayloadScore:
	score: float
	reason: str
	has_primary_hint: bool
	negative_hits: int = 0


def discover_job_feeds(
	page_url: str,
	*,
	session: Optional[requests.Session] = None,
	timeout: int = DEFAULT_TIMEOUT,
	debug: bool = False,
) -> List[FeedCandidate]:
	"""Attempt to locate backing JSON feeds that power a dynamic careers page."""

	client = session or requests.Session()
	html = fetch_html(page_url, session=client, timeout=timeout)

	text_sources = [html]
	pending_scripts = _extract_script_urls(html, page_url)
	seen_scripts: set[str] = set()

	while pending_scripts and len(seen_scripts) < MAX_SCRIPT_FETCHES:
		script_url = pending_scripts.pop(0)
		if script_url in seen_scripts:
			continue
		seen_scripts.add(script_url)

		try:
			response = client.get(script_url, timeout=timeout)
			response.raise_for_status()
		except requests.RequestException:
			if debug:
				print(f"[feed-discovery] failed script fetch: {script_url}")
			continue

		body = response.text[:MAX_SCRIPT_BYTES]
		if body:
			if debug:
				print(f"[feed-discovery] inspecting script: {script_url}")
			text_sources.append(body)
			extra_script_urls = _extract_importmap_targets(body, script_url)
			for extra_url in extra_script_urls:
				if extra_url not in seen_scripts and extra_url not in pending_scripts:
					pending_scripts.append(extra_url)

	raw_urls = _extract_candidate_urls(text_sources, page_url)
	candidates: List[FeedCandidate] = []
	if debug and raw_urls:
		print("[feed-discovery] candidate URLs:")
		for raw in raw_urls:
			print(f"  - {raw}")

	for candidate_url in list(raw_urls)[:MAX_ENDPOINT_TRIES]:
		try:
			result = _probe_endpoint(candidate_url, client=client, timeout=timeout)
		except FetchError:
			if debug:
				print(f"[feed-discovery] probe failed: {candidate_url}")
			continue
		if result:
			if debug:
				print(
					"[feed-discovery] JSON detected: "
					f"{candidate_url} (score={result.score:.2f})"
				)
			candidates.append(result)

	inline_candidates = _extract_inline_json_candidates(
		html,
		page_url,
		debug=debug,
	)
	if inline_candidates and debug:
		print(f"[feed-discovery] inline JSON candidates: {len(inline_candidates)}")
	candidates.extend(inline_candidates)

	candidates.sort(key=lambda item: item.score, reverse=True)
	return candidates


def _extract_script_urls(html: str, base_url: str) -> List[str]:
	pattern = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
	urls: List[str] = []
	for match in pattern.finditer(html):
		src = match.group(1)
		if not src:
			continue
		if src.startswith("data:"):
			continue
		full_url = urljoin(base_url, src)
		urls.append(full_url)
	return urls


def _extract_candidate_urls(text_sources: Iterable[str], base_url: str) -> List[str]:
	found: List[str] = []
	seen = set()
	for text in text_sources:
		for match in URL_PATTERN.finditer(text):
			raw = match.group(1)
			if not raw:
				continue
			if raw.startswith("javascript:") or raw.startswith("mailto:"):
				continue
			normalized = urljoin(base_url, raw)
			if normalized in seen:
				continue
			if not _url_has_keyword(normalized):
				continue
			seen.add(normalized)
			found.append(normalized)
	return found


def _extract_importmap_targets(body: str, base_url: str) -> List[str]:
	try:
		data = json.loads(body)
	except ValueError:
		return []

	targets: List[str] = []

	def add_url(raw: str) -> None:
		if not isinstance(raw, str):
			return
		if raw.startswith("data:"):
			return
		full = urljoin(base_url, raw)
		if _url_has_keyword(full):
			targets.append(full)
		elif full.endswith(('.js', '.mjs', '.json')):
			targets.append(full)

	if isinstance(data, dict):
		imports = data.get("imports")
		if isinstance(imports, dict):
			for url in imports.values():
				add_url(url)

		scopes = data.get("scopes")
		if isinstance(scopes, dict):
			for scope in scopes.values():
				if isinstance(scope, dict):
					for url in scope.values():
						add_url(url)

	return targets


def _url_has_keyword(url: str) -> bool:
	lowered = url.lower()
	return any(keyword in lowered for keyword in KEYWORDS)


def _probe_endpoint(
	url: str,
	*,
	client: requests.Session,
	timeout: int = DEFAULT_TIMEOUT,
) -> Optional[FeedCandidate]:
	headers = {"Accept": "application/json, text/plain;q=0.9"}
	try:
		response = client.get(url, timeout=timeout, headers=headers)
		response.raise_for_status()
	except requests.RequestException as exc:  # pragma: no cover - network dependent
		raise FetchError(str(exc))

	content_type = response.headers.get("Content-Type", "")
	if "json" not in content_type.lower():
		try:
			payload = response.json()
		except ValueError:
			return None
	else:
		try:
			payload = response.json()
		except ValueError:
			return None

	score_info = score_payload(payload)
	if score_info.score <= 0:
		return None

	return FeedCandidate(
		url=url,
		score=score_info.score,
		reason=score_info.reason,
		payload=payload,
		content_type=content_type,
		status_code=response.status_code,
	)


MAX_SAMPLE_ITEMS = 6
MAX_SCORE_DEPTH = 4


def score_payload(payload: object, *, depth: int = 0) -> PayloadScore:
	score = 0.0
	reasons: List[str] = []
	has_primary = False
	negative_hits = 0

	if depth > MAX_SCORE_DEPTH:
		return PayloadScore(0.0, "depth limit", has_primary)

	if isinstance(payload, list):
		if payload and isinstance(payload[0], dict):
			key_score, key_reason, key_primary, key_neg = _score_keys(payload[0].keys())
			if key_score:
				score += key_score
				reasons.append(f"item keys: {key_reason}")
			has_primary = has_primary or key_primary
			negative_hits += key_neg
			if len(payload) >= 5:
				score += 1.0
				reasons.append("list length >= 5")
		for item in payload[:MAX_SAMPLE_ITEMS]:
			child = score_payload(item, depth=depth + 1)
			if child.score:
				score += child.score * 0.6
				if child.reason:
					reasons.append(child.reason)
			has_primary = has_primary or child.has_primary_hint
			negative_hits += child.negative_hits
	elif isinstance(payload, dict):
		key_score, key_reason, key_primary, key_neg = _score_keys(payload.keys())
		if key_score:
			score += key_score
			reasons.append(f"keys: {key_reason}")
		has_primary = has_primary or key_primary
		negative_hits += key_neg

		for key, value in payload.items():
			child = score_payload(value, depth=depth + 1)
			if child.score:
				score += child.score * 0.6
				if child.reason:
					reasons.append(f"{key}: {child.reason}")
			has_primary = has_primary or child.has_primary_hint
			negative_hits += child.negative_hits
	else:
		try:
			text = json.dumps(payload)
		except (TypeError, ValueError):  # pragma: no cover - defensive
			text = str(payload)
		lowered = text.lower()
		if any(token in lowered for token in PRIMARY_TEXT_TOKENS):
			score += 1.2
			reasons.append("text includes primary job token")
			has_primary = True
		elif _contains_job_keywords(lowered):
			score += 0.6
			reasons.append("text mentions job keyword")

	if not has_primary:
		try:
			serialized = json.dumps(payload)
		except (TypeError, ValueError):
			serialized = str(payload)
		lower = serialized.lower()
		if any(token in lower for token in PRIMARY_TEXT_TOKENS):
			score += 1.0
			reasons.append("serialized includes primary job token")
			has_primary = True
		elif any(keyword in lower for keyword in PRIMARY_JOB_KEYWORDS):
			score += 0.8
			reasons.append("serialized mentions job keyword")
			has_primary = True

	if negative_hits and not has_primary:
		return PayloadScore(0.0, "filtered by negative keywords", False, negative_hits=negative_hits)
	elif negative_hits:
		score *= max(0.4, 1 - 0.1 * negative_hits)
		reasons.append("contains consent-related keys")

	if score <= 0:
		return PayloadScore(0.0, "", has_primary, negative_hits=negative_hits)

	return PayloadScore(score, "; ".join(reasons), has_primary, negative_hits=negative_hits)


def _score_keys(keys: Iterable[str]) -> Tuple[float, str, bool, int]:
	primary_hits: List[str] = []
	secondary_hits: List[str] = []
	score = 0.0
	negative_hits = 0
	for key in keys:
		lowered = key.lower()
		if any(neg in lowered for neg in NEGATIVE_KEYWORDS):
			negative_hits += 1
		primary_match = any(token in lowered for token in PRIMARY_JOB_KEYWORDS)
		secondary_match = any(token in lowered for token in SECONDARY_JOB_KEYWORDS)
		if primary_match:
			primary_hits.append(key)
			score += 1.2
		elif secondary_match:
			secondary_hits.append(key)
			score += 0.6
	if primary_hits or secondary_hits:
		reason = ", ".join(sorted(primary_hits + secondary_hits)[:6])
	else:
		reason = ""
	return score, reason, bool(primary_hits), negative_hits


def _contains_job_keywords(text: str) -> bool:
	lowered = text.lower()
	return any(keyword in lowered for keyword in KEYWORDS)


def _extract_inline_json_candidates(html: str, base_url: str, debug: bool) -> List[FeedCandidate]:
	candidates: List[FeedCandidate] = []
	for label, pattern, mode in INLINE_JSON_PATTERNS:
		for match in pattern.finditer(html):
			raw = match.group(1)
			if not raw:
				continue
			try:
				if mode == "json_parse":
					try:
						decoded = json.loads(f'"{raw}"')
					except json.JSONDecodeError:
						decoded = raw.encode("utf-8").decode("unicode_escape")
				else:
					decoded = raw
				data = json.loads(decoded)
			except json.JSONDecodeError:
				if debug:
					print(f"[feed-discovery] failed to decode inline JSON for {label}")
				continue

			top_nodes = _find_top_scoring_nodes(data)
			seen_payloads: set[int] = set()
			for score_info, node, pointer in top_nodes:
				items, items_key = _extract_items_from_node(node)
				if not isinstance(items, list) or not items:
					continue
				items_id = id(items)
				if items_id in seen_payloads:
					continue
				seen_payloads.add(items_id)

				items_score = score_payload(items)
				if items_score.score <= 0.5:
					continue
				final_score = items_score.score + min(score_info.score * 0.2, 25)
				reason_fragment = items_score.reason or score_info.reason
				pointer_display = pointer or "root"

				payload: dict[str, object] = {
					"source": {
						"type": label,
						"pointer": pointer_display,
						"items_key": items_key or ("self" if node is items else None),
					},
					"items": items,
				}
				if node is not items and isinstance(node, dict):
					payload["node"] = node

				candidate = FeedCandidate(
					url=f"{base_url}#{label}",
					score=final_score,
					reason=f"inline {label} @ {pointer_display}: {reason_fragment}",
					payload=payload,
					content_type="application/json; inline",
					status_code=200,
				)
				candidates.append(candidate)
				if debug:
					print(
						"[feed-discovery] inline JSON candidate from "
						f"{label} (pointer={pointer_display}, score={candidate.score:.2f})"
					)
				if len(candidates) >= 3:
					break
	return candidates


def _find_top_scoring_nodes(data: object) -> List[Tuple[PayloadScore, object, str]]:
	results: List[Tuple[PayloadScore, object, str]] = []
	visited: set[int] = set()
	count = 0

	def visit(node: object, pointer: str, depth: int) -> None:
		nonlocal count
		if depth > MAX_INLINE_DEPTH or count >= MAX_INLINE_NODE_VISITS:
			return
		node_id = id(node)
		if node_id in visited:
			return
		visited.add(node_id)
		count += 1

		score_info = score_payload(node)
		if score_info.score > 0:
			results.append((score_info, node, pointer))

		if isinstance(node, dict):
			for key, value in node.items():
				child_pointer = f"{pointer}.{key}" if pointer else key
				visit(value, child_pointer, depth + 1)
		elif isinstance(node, list):
			for idx, value in enumerate(node[:MAX_INLINE_LIST_SAMPLES]):
				child_pointer = f"{pointer}[{idx}]" if pointer else f"[{idx}]"
				visit(value, child_pointer, depth + 1)

	visit(data, "", 0)
	results.sort(key=lambda entry: entry[0].score, reverse=True)
	return results


def _extract_items_from_node(node: object) -> Tuple[Optional[List[object]], Optional[str]]:
	if isinstance(node, list):
		return node, None
	if isinstance(node, dict):
		for key in INLINE_LIST_KEYS:
			value = node.get(key)
			if isinstance(value, list) and value:
				return value, key
		for key, value in node.items():
			if isinstance(value, list) and value:
				return value, key
	return None, None


def save_best_feed(
	page_url: str,
	destination: Path | str,
	*,
	session: Optional[requests.Session] = None,
	timeout: int = DEFAULT_TIMEOUT,
	debug: bool = False,
) -> FeedCandidate:
	"""Discover feeds for a careers page and persist the highest scoring payload."""

	candidates = discover_job_feeds(
		page_url,
		session=session,
		timeout=timeout,
		debug=debug,
	)
	if not candidates:
		raise FetchError(f"No job feed detected for {page_url}")

	best = candidates[0]
	path = Path(destination)
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(best.payload, indent=2), encoding="utf-8")
	return best

