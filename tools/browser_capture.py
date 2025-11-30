"""Headless browser utilities for capturing dynamic job feeds."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .feed_discovery import FeedCandidate, KEYWORDS, PayloadScore, score_payload


class BrowserCaptureError(RuntimeError):
    """Raised when the browser-based capture fails."""


@dataclass(slots=True)
class BrowserCaptureSummary:
    """Summary of the captured feed and persistence target."""

    feed: FeedCandidate
    saved_to: Path
    captures_dir: Optional[Path] = None


@dataclass(slots=True)
class CapturedPayload:
    url: str
    status_code: int
    payload: object
    score: PayloadScore
    content_type: str


async def _capture_with_playwright(
    url: str,
    *,
    keywords: Iterable[str],
    browser: str = "chromium",
    timeout_ms: int = 250000,
    wait_after_load: float = 5.0,
    max_candidates: int = 10,
    debug: bool = False,
) -> Tuple[List[FeedCandidate], List[CapturedPayload]]:
    try:
        from playwright.async_api import async_playwright  # type: ignore[import]
        from playwright.async_api import TimeoutError as PlaywrightTimeout  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - runtime environment specific
        raise BrowserCaptureError(
            "playwright is not installed. Run 'pip install playwright' and 'playwright install chromium'"
        ) from exc

    candidates: List[FeedCandidate] = []
    all_payloads: List[CapturedPayload] = []
    seen_urls: set[str] = set()
    lock = asyncio.Lock()
    keyword_list = [k.lower() for k in keywords]

    async def process_response(response) -> None:  # type: ignore[no-untyped-def]
        try:
            url_lower = response.url.lower()
            content_type = response.headers.get("content-type", "")
            is_json_like = "json" in content_type.lower() or url_lower.endswith((".json", ".geojson"))

            if response.status >= 400:
                if debug:
                    print(f"[browser-capture] skipping {response.url} (status {response.status})")
                return

            if is_json_like:
                try:
                    payload = await response.json()
                except Exception:
                    if debug:
                        print(f"[browser-capture] failed json() for {response.url}")
                    return
            else:
                try:
                    txt = await response.text()
                except Exception:
                    return
                if not txt.strip().startswith(("{", "[")):
                    if debug and any(keyword in url_lower for keyword in keyword_list):
                        print(f"[browser-capture] non-json body for {response.url}")
                    return
                try:
                    payload = json.loads(txt)
                except ValueError:
                    if debug:
                        print(f"[browser-capture] invalid JSON text for {response.url}")
                    return
        except Exception:
            return

        score_info = score_payload(payload)

        async with lock:
            if response.url in seen_urls:
                return
            seen_urls.add(response.url)

            captured = CapturedPayload(
                url=response.url,
                status_code=response.status,
                payload=payload,
                score=score_info,
                content_type=content_type,
            )
            all_payloads.append(captured)

            if score_info.score <= 0:
                if debug:
                    print(
                        f"[browser-capture] rejected {response.url} (score={score_info.score:.2f}, reason='{score_info.reason}')"
                    )
                return

            if debug:
                print(
                    f"[browser-capture] accepted {response.url} (score={score_info.score:.2f}, reason='{score_info.reason}')"
                )

            candidates.append(
                FeedCandidate(
                    url=response.url,
                    score=score_info.score,
                    reason=score_info.reason or "playwright capture",
                    payload=payload,
                    content_type=content_type,
                    status_code=response.status,
                )
            )

    async with async_playwright() as p:
        try:
            launcher = getattr(p, browser)
        except AttributeError as exc:  # pragma: no cover - defensive
            raise BrowserCaptureError(f"Playwright browser '{browser}' is not available") from exc

        browser_instance = await launcher.launch(headless=True)
        context = await browser_instance.new_context()
        page = await context.new_page()
        page.on("response", lambda response: asyncio.create_task(process_response(response)))

        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except PlaywrightTimeout:
            if debug:
                print(f"[browser-capture] navigation timeout for {url}")

        await asyncio.sleep(wait_after_load)
        await browser_instance.close()

    if not candidates:
        unique_candidates: dict[str, FeedCandidate] = {}
    else:
        unique_candidates = {candidate.url: candidate for candidate in candidates}

    sorted_candidates = sorted(unique_candidates.values(), key=lambda item: item.score, reverse=True)
    return sorted_candidates[:max_candidates], all_payloads


def capture_feed_to_file(
    url: str,
    destination: Path | str,
    *,
    keywords: Optional[Iterable[str]] = None,
    browser: str = "chromium",
    timeout_ms: int = 25000,
    wait_after_load: float = 5.0,
    max_candidates: int = 10,
    debug: bool = False,
    dump_dir: Optional[Path | str] = None,
) -> BrowserCaptureSummary:
    """Launch a headless browser, capture job feed responses, and persist the best one."""

    keyword_stream = list(keywords) if keywords is not None else KEYWORDS
    candidates, captured_payloads = asyncio.run(
        _capture_with_playwright(
            url,
            keywords=keyword_stream,
            browser=browser,
            timeout_ms=timeout_ms,
            wait_after_load=wait_after_load,
            max_candidates=max_candidates,
            debug=debug,
        )
    )

    if dump_dir:
        dump_path = Path(dump_dir)
        dump_path.mkdir(parents=True, exist_ok=True)
        manifest: List[dict] = []
        for idx, captured in enumerate(captured_payloads):
            score_tag = f"{captured.score.score:.2f}".replace(".", "_")
            filename = f"{idx:02d}_{_slugify_url(captured.url)}_{score_tag}.json"
            file_path = dump_path / filename
            try:
                file_path.write_text(json.dumps(captured.payload, indent=2), encoding="utf-8")
            except TypeError:
                # Non-serializable payloads fallback to raw string representation
                file_path.write_text(str(captured.payload), encoding="utf-8")
            manifest.append(
                {
                    "url": captured.url,
                    "status": captured.status_code,
                    "score": captured.score.score,
                    "reason": captured.score.reason,
                    "has_primary_hint": captured.score.has_primary_hint,
                    "negative_hits": captured.score.negative_hits,
                    "content_type": captured.content_type,
                    "filename": filename,
                }
            )
        (dump_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    else:
        dump_path = None

    if not candidates:
        raise BrowserCaptureError(f"No suitable JSON responses captured from {url}")

    best = candidates[0]
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(best.payload, indent=2), encoding="utf-8")

    return BrowserCaptureSummary(feed=best, saved_to=path, captures_dir=dump_path)


def _slugify_url(url: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", url)
    safe = safe.strip("-")
    return safe[:60] or "capture"

