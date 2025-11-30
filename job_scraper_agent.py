"""Simple job scraper that uses Playwright + optional LLM cleaning."""
from __future__ import annotations

import os
from urllib.parse import urlparse

from dotenv import load_dotenv

from browser_client import BrowserMCPError, BrowserMCPTimeoutError, fetch_page_markdown
from content_cleaner import clean_job_content
from logging_utils import get_logger

load_dotenv()

logger = get_logger(__name__)


class URLValidationError(ValueError):
    """Raised when the provided URL is invalid or unsupported."""


class JobScraperAgent:
    """Simple wrapper for scraping job postings via Playwright."""

    def __init__(self, timeout: float | None = None, clean_with_llm: bool = True) -> None:
        self.timeout = timeout
        self.clean_with_llm = clean_with_llm
        self.name = "role_scraper_agent"

    @staticmethod
    def _validate_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise URLValidationError("URL must start with http:// or https://")
        if not parsed.netloc:
            raise URLValidationError("URL must include a hostname")
        return url

    def run(self, url: str) -> str:
        """Fetch and return job text from the given URL."""
        validated_url = self._validate_url(url)
        logger.info("role_scraper_agent received URL %s", validated_url)
        logger.info("Scraping with Playwright for %s", validated_url)
        
        if self.timeout is not None:
            raw_content = fetch_page_markdown(validated_url, timeout=self.timeout)
        else:
            raw_content = fetch_page_markdown(validated_url)
        
        logger.info("Successfully retrieved %d characters from %s", len(raw_content), validated_url)
        
        # Optionally clean with LLM
        if self.clean_with_llm:
            logger.info("Cleaning content with LLM...")
            cleaned_content = clean_job_content(raw_content, validated_url)
            return cleaned_content
        
        return raw_content


def run_job_scraper(url: str, *, timeout: float | None = None, clean_with_llm: bool = True) -> str:
    """Entry point used by the CLI to obtain job text.
    
    Args:
        url: Job posting URL to scrape
        timeout: Optional timeout in seconds
        clean_with_llm: If True, use Gemini to extract only job content (recommended for varied sites)
    """
    agent = JobScraperAgent(timeout=timeout, clean_with_llm=clean_with_llm)
    try:
        return agent.run(url)
    except (BrowserMCPTimeoutError, BrowserMCPError, URLValidationError):
        raise
