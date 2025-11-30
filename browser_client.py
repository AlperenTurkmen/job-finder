"""BrowserMCP client helper module - SIMPLIFIED VERSION.

NOTE: BrowserMCP requires a running browser extension + MCP server.
This implementation uses direct HTTP/WebSocket calls as a fallback.
For full BrowserMCP integration, you need the browser extension installed
and configured to communicate with your MCP server.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from dotenv import load_dotenv
from tenacity import AsyncRetrying, RetryError, retry_if_exception_type, stop_after_attempt, wait_exponential

from logging_utils import get_logger

load_dotenv()

logger = get_logger(__name__)


class BrowserMCPError(RuntimeError):
    """Base error raised for BrowserMCP issues."""


class BrowserMCPTimeoutError(BrowserMCPError):
    """Raised when BrowserMCP does not respond before the timeout."""


class BrowserMCPConfigurationError(BrowserMCPError):
    """Raised when the BrowserMCP client is misconfigured."""


@dataclass(slots=True)
class BrowserMCPConfig:
    """Runtime configuration for connecting to BrowserMCP."""

    endpoint: str
    api_key: Optional[str]
    project: Optional[str]
    timeout: float = 25.0

    @classmethod
    def from_env(cls) -> "BrowserMCPConfig":
        endpoint = os.getenv("BROWSERMCP_WS_ENDPOINT")
        if not endpoint:
            raise BrowserMCPConfigurationError(
                "BROWSERMCP_WS_ENDPOINT must be provided to reach BrowserMCP"
            )
        return cls(
            endpoint=endpoint,
            api_key=os.getenv("BROWSERMCP_API_KEY"),
            project=os.getenv("BROWSERMCP_PROJECT"),
            timeout=float(os.getenv("BROWSERMCP_TIMEOUT", "25")),
        )


def _ensure_event_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


async def _invoke_browser_via_playwright(config: BrowserMCPConfig, url: str, timeout: float) -> str:
    """Use Playwright to fetch fully rendered page content."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise BrowserMCPConfigurationError(
            "playwright package is required. Install: pip install playwright && playwright install chromium"
        ) from exc

    logger.info("Playwright navigate -> %s", url)
    
    async with async_playwright() as p:
        # Launch browser (headless mode)
        browser = await p.chromium.launch(headless=True)
        logger.debug("Browser launched")
        
        # Create a new page
        page = await browser.new_page()
        
        # Navigate to URL and wait for network to be idle
        try:
            logger.debug("Navigating to %s (timeout=%ds)", url, timeout)
            await page.goto(url, wait_until="networkidle", timeout=int(timeout * 1000))
            logger.debug("Page loaded, extracting content")
            
            # Try to find job-specific content sections first
            job_content = None
            
            # Common selectors for job posting content
            job_selectors = [
                "main",  # Most sites use <main> for primary content
                "article",  # Job postings often in <article>
                "[role='main']",  # ARIA role
                ".job-description",  # Common class names
                ".job-details",
                ".job-content",
                "#job-description",
                "#job-details",
                ".posting-description",  # Greenhouse
                ".job-posting",
            ]
            
            for selector in job_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        job_content = await element.inner_text()
                        if job_content and len(job_content.strip()) > 100:
                            logger.debug("Found job content using selector: %s", selector)
                            break
                except Exception:
                    continue
            
            # Fallback to body if no specific content found
            if not job_content:
                logger.debug("No specific job content selector found, using body")
                job_content = await page.inner_text("body")
            
            text_content = job_content
            logger.info("Successfully retrieved %d characters", len(text_content))
            
        except Exception as exc:
            logger.error("Playwright navigation error: %s", exc)
            raise BrowserMCPTimeoutError(f"Failed to load {url}: {exc}") from exc
        finally:
            await browser.close()
            logger.debug("Browser closed")
        
        return text_content


def _extract_markdown(observation: Any) -> str:
    if observation is None:
        return ""
    if isinstance(observation, str):
        return observation
    if isinstance(observation, bytes):
        return observation.decode("utf-8", errors="ignore")
    if isinstance(observation, dict):
        for key in ("markdown", "text", "content", "body"):
            value = observation.get(key)
            if isinstance(value, str) and value.strip():
                return value
        if "observations" in observation:
            return _extract_from_iterable(observation["observations"])
        if "output" in observation:
            return _extract_markdown(observation["output"])
    if isinstance(observation, Iterable):
        return _extract_from_iterable(observation)
    return str(observation)


def _extract_from_iterable(items: Iterable[Any]) -> str:
    chunks: list[str] = []
    for item in items:
        text = _extract_markdown(item)
        if text:
            chunks.append(text)
    return "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip())


async def _fetch_once(url: str, config: BrowserMCPConfig) -> str:
    text_content = await _invoke_browser_via_playwright(config, url, timeout=config.timeout)
    if not text_content.strip():
        raise BrowserMCPError("Playwright returned no text content for the requested page")
    return text_content


def _safe_preview(payload: Any) -> str:
    try:
        if isinstance(payload, (dict, list)):
            return json.dumps(payload)[:500]
        return str(payload)[:500]
    except Exception:  # pragma: no cover - defensive path
        return "<unserializable>"


async def _fetch_with_retry(url: str, config: BrowserMCPConfig) -> str:
    retrying = AsyncRetrying(
        retry=retry_if_exception_type((BrowserMCPError, ConnectionError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async for attempt in retrying:
        with attempt:
            return await _fetch_once(url, config)
    raise BrowserMCPError("Unexpected retry termination")


def fetch_page_markdown(url: str, timeout: float | None = None) -> str:
    """Fetch the rendered job page via BrowserMCP and return raw markdown."""
    config = BrowserMCPConfig.from_env()
    if timeout is not None:
        config = BrowserMCPConfig(
            endpoint=config.endpoint,
            api_key=config.api_key,
            project=config.project,
            timeout=timeout,
        )

    async def runner() -> str:
        return await _fetch_with_retry(url, config)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(runner())
        except RetryError as exc:  # pragma: no cover - handled in outer scope
            raise exc.last_attempt.exception()
    else:
        if loop.is_running():
            raise RuntimeError(
                "fetch_page_markdown cannot be executed within an active event loop. "
                "Use asyncio and call _fetch_with_retry directly instead."
            )
        try:
            return loop.run_until_complete(runner())
        except RetryError as exc:  # pragma: no cover - handled in outer scope
            raise exc.last_attempt.exception()
