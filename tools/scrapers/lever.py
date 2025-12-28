"""Scraper for Lever ATS job pages.

Lever is used by many tech companies including:
- Netflix, Twitch, Cloudflare, etc.

URL patterns:
- jobs.lever.co/{company}/{job_id}
"""

from .base import BaseScraper, ScrapedJob


class LeverScraper(BaseScraper):
    """Scraper for Lever ATS pages."""
    
    URL_PATTERNS = ["lever.co"]
    
    async def scrape_job_listing(self, url: str, page) -> ScrapedJob:
        """Extract job data from a Lever job page."""
        
        # TODO: Implement Lever-specific selectors
        # Common selectors:
        # - Job title: h2.posting-headline
        # - Location: .location, .posting-categories .sort-by-time
        # - Description: .posting-content
        # - Requirements: .posting-requirements
        
        title = await self.extract_text(page, "h2.posting-headline")
        location = await self.extract_text(page, ".location")
        description = await self.extract_text(page, ".posting-content")
        
        return ScrapedJob(
            company="",  # Extract from page or URL
            role=title,
            location=location,
            description=description,
            responsibilities=[],
            qualifications=[],
        )
