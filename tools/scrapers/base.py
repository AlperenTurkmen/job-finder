"""Base scraper class and registry for website-specific scrapers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class ScrapedJob:
    """Standardized output from any scraper."""
    company: str
    role: str
    location: str
    description: str
    responsibilities: list[str]
    qualifications: list[str]
    salary: str = ""
    job_type: str = ""
    tech_stack: list[str] | None = None
    raw_html: str = ""


class BaseScraper(ABC):
    """Abstract base class for website-specific scrapers.
    
    Subclasses must implement:
    - URL_PATTERNS: list of patterns this scraper handles
    - scrape_job_listing(): extract structured data from a job page
    
    Example:
        class GreenhouseScraper(BaseScraper):
            URL_PATTERNS = ["greenhouse.io", "boards.greenhouse.io"]
            
            async def scrape_job_listing(self, url: str, page) -> ScrapedJob:
                # Greenhouse-specific extraction logic
                ...
    """
    
    URL_PATTERNS: ClassVar[list[str]] = []
    
    def __init_subclass__(cls, **kwargs):
        """Auto-register subclasses with the registry."""
        super().__init_subclass__(**kwargs)
        if cls.URL_PATTERNS:
            ScraperRegistry.register(cls)
    
    @classmethod
    def matches_url(cls, url: str) -> bool:
        """Check if this scraper handles the given URL."""
        return any(pattern in url.lower() for pattern in cls.URL_PATTERNS)
    
    @abstractmethod
    async def scrape_job_listing(self, url: str, page) -> ScrapedJob:
        """Scrape a job listing page and return structured data.
        
        Args:
            url: The job listing URL
            page: Playwright page object (already navigated to URL)
            
        Returns:
            ScrapedJob with extracted fields
        """
        ...
    
    async def extract_text(self, page, selector: str) -> str:
        """Helper to safely extract text from a selector."""
        try:
            element = await page.query_selector(selector)
            if element:
                return (await element.inner_text()).strip()
        except Exception:
            pass
        return ""
    
    async def extract_list(self, page, selector: str) -> list[str]:
        """Helper to extract a list of text items from matching elements."""
        try:
            elements = await page.query_selector_all(selector)
            return [
                (await el.inner_text()).strip()
                for el in elements
                if await el.inner_text()
            ]
        except Exception:
            return []


class ScraperRegistry:
    """Registry of available scrapers."""
    
    _scrapers: ClassVar[list[type[BaseScraper]]] = []
    
    @classmethod
    def register(cls, scraper_class: type[BaseScraper]) -> None:
        """Register a scraper class."""
        if scraper_class not in cls._scrapers:
            cls._scrapers.append(scraper_class)
    
    @classmethod
    def get_scraper_for_url(cls, url: str) -> BaseScraper | None:
        """Find and instantiate the appropriate scraper for a URL."""
        for scraper_class in cls._scrapers:
            if scraper_class.matches_url(url):
                return scraper_class()
        return None
    
    @classmethod
    def list_scrapers(cls) -> list[str]:
        """List all registered scraper names."""
        return [s.__name__ for s in cls._scrapers]
