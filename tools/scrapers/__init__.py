"""Website-specific job scrapers.

Each scraper handles a specific ATS or company careers page format.
Use get_scraper(url) to auto-detect the appropriate scraper.
"""

from .base import BaseScraper, ScraperRegistry

__all__ = ["BaseScraper", "ScraperRegistry", "get_scraper"]


def get_scraper(url: str) -> BaseScraper | None:
    """Return the appropriate scraper for a URL, or None if no match."""
    return ScraperRegistry.get_scraper_for_url(url)
