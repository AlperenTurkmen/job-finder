"""Scraper for Workday ATS job pages.

Workday is used by many large enterprises including:
- Nike, Apple, Amazon, Netflix, etc.

URL patterns:
- {company}.wd5.myworkdayjobs.com/{path}/{job_id}
- Various subdomains: wd1, wd2, wd3, wd5
"""

from .base import BaseScraper, ScrapedJob


class WorkdayScraper(BaseScraper):
    """Scraper for Workday ATS pages."""
    
    URL_PATTERNS = ["myworkdayjobs.com", "workday.com/jobs"]
    
    async def scrape_job_listing(self, url: str, page) -> ScrapedJob:
        """Extract job data from a Workday job page.
        
        Note: Workday pages are heavily JS-rendered and may require
        waiting for specific elements to load.
        """
        
        # TODO: Implement Workday-specific selectors
        # Workday pages are complex - may need to wait for React/Angular rendering
        # Common selectors (vary by implementation):
        # - Job title: [data-automation-id="jobPostingHeader"]
        # - Location: [data-automation-id="locations"]
        # - Description: [data-automation-id="jobPostingDescription"]
        
        # Wait for dynamic content
        try:
            await page.wait_for_selector("[data-automation-id='jobPostingHeader']", timeout=5000)
        except Exception:
            pass
        
        title = await self.extract_text(page, "[data-automation-id='jobPostingHeader']")
        location = await self.extract_text(page, "[data-automation-id='locations']")
        description = await self.extract_text(page, "[data-automation-id='jobPostingDescription']")
        
        return ScrapedJob(
            company="",
            role=title,
            location=location,
            description=description,
            responsibilities=[],
            qualifications=[],
        )
