"""Netflix Careers Scraper - Extract job listings from Netflix's careers portal.

This module provides tools to scrape job listings from Netflix's careers website
(explore.jobs.netflix.net), which is powered by Eightfold ATS.

Primary Function:
    scrape_netflix_jobs(location, query) -> list[NetflixJobListing]
    
    This is the main function an agent should use to retrieve Netflix job listings.

Example Usage:
    ```python
    import asyncio
    from tools.scrapers.netflix import scrape_netflix_jobs
    
    # Get all jobs in United Kingdom (default)
    jobs = asyncio.run(scrape_netflix_jobs())
    
    # Get jobs in a specific location
    jobs = asyncio.run(scrape_netflix_jobs(location="Madrid"))
    jobs = asyncio.run(scrape_netflix_jobs(location="London"))
    jobs = asyncio.run(scrape_netflix_jobs(location="Amsterdam"))
    
    # Search for specific roles
    jobs = asyncio.run(scrape_netflix_jobs(location="United Kingdom", query="engineer"))
    
    # Get all jobs worldwide (no location filter)
    jobs = asyncio.run(scrape_netflix_jobs(location=None))
    
    # Access job data
    for job in jobs:
        print(f"Title: {job.title}")
        print(f"Location: {job.location}")
        print(f"URL: {job.job_url}")
    ```

Return Data Structure:
    Returns a list of NetflixJobListing objects with:
    - title (str): Job title, e.g., "Senior Software Engineer"
    - location (str): Job location, e.g., "London, United Kingdom"
    - job_url (str): Direct URL to the job posting

Supported Locations (examples):
    - "United Kingdom", "London", "England"
    - "Spain", "Madrid", "Barcelona"  
    - "Netherlands", "Amsterdam"
    - "United States", "Los Angeles", "New York"
    - "Germany", "Berlin"
    - Or any location listed on Netflix careers

Notes:
    - This function uses Playwright for browser automation (headless by default)
    - The scraper handles lazy-loading by scrolling to load all results
    - Network requests may take 5-15 seconds depending on result count
"""

import asyncio
from dataclasses import dataclass
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright.async_api import async_playwright, Page

try:
    from tools.scrapers.base import BaseScraper, ScrapedJob
except ImportError:
    # Fallback if base.py doesn't exist or for standalone execution
    from typing import Protocol
    
    class BaseScraper:
        """Minimal base scraper class."""
        async def extract_text(self, page, selector):
            try:
                el = await page.query_selector(selector)
                return (await el.inner_text()).strip() if el else ""
            except:
                return ""
    
    class ScrapedJob:
        """Minimal scraped job class."""
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)


@dataclass
class NetflixJobListing:
    """A job listing from Netflix search results.
    
    Attributes:
        title: The job title (e.g., "Senior Software Engineer")
        location: Primary job location (e.g., "London, United Kingdom")
        locations: All locations for this role (list, for multi-location jobs)
        department: Department name (e.g., "Advertising", "Engineering")
        business_unit: Business unit (e.g., "Streaming", "Games")
        work_location_option: Work arrangement - "onsite", "remote", or "hybrid"
        job_id: Netflix job reference number (e.g., "JR37877")
        job_url: Direct URL to the job posting on Netflix careers
    """
    title: str
    location: str
    locations: list[str]
    department: str
    business_unit: str
    work_location_option: str
    job_id: str
    job_url: str


class NetflixScraper(BaseScraper):
    """Scraper for Netflix careers pages (Eightfold ATS)."""
    
    URL_PATTERNS = ["explore.jobs.netflix.net", "jobs.netflix.com"]
    
    async def scrape_job_listing(self, url: str, page: Page) -> ScrapedJob:
        """Extract job data from a Netflix job detail page."""
        
        # Wait for content to load
        try:
            await page.wait_for_selector(".position-title", timeout=10000)
        except Exception:
            pass
        
        title = await self.extract_text(page, ".position-title")
        location = await self.extract_text(page, ".position-location")
        description = await self.extract_text(page, ".position-job-description")
        
        return ScrapedJob(
            company="Netflix",
            role=title,
            location=location,
            description=description,
            responsibilities=[],
            qualifications=[],
        )
    
    async def scrape_job_search(self, url: str, page: Page) -> list[NetflixJobListing]:
        """Scrape all job listings from Netflix search results page.
        
        Args:
            url: Netflix careers search URL
            page: Playwright page object (already navigated to URL)
            
        Returns:
            List of job listings with title, location, and URL
        """
        import json
        import re
        
        jobs: list[NetflixJobListing] = []
        
        # Wait for position cards to load
        try:
            await page.wait_for_selector(".position-card", timeout=15000)
        except Exception:
            pass
        
        # Extract job data from the page's embedded JSON (includes IDs for URLs)
        html_content = await page.content()
        
        # Find complete job objects using a more comprehensive regex
        # Captures all fields between { and }
        job_pattern = r'\{"id":\s*(\d+),\s*"name":\s*"([^"]+)",\s*"location":\s*"([^"]*)",\s*"locations":\s*\[([^\]]*)\][^}]*"department":\s*"([^"]*)"[^}]*"business_unit":\s*"([^"]*)"[^}]*"ats_job_id":\s*"([^"]*)"[^}]*"work_location_option":\s*"([^"]*)"'
        matches = re.findall(job_pattern, html_content)
        
        if matches:
            for match in matches:
                job_id_num, name, location, locations_str, department, business_unit, ats_job_id, work_option = match
                
                # Parse locations array
                locations = re.findall(r'"([^"]+)"', locations_str)
                
                # Decode HTML entities (e.g., &amp; -> &)
                import html
                department = html.unescape(department)
                name = html.unescape(name)
                
                job_url = f"https://explore.jobs.netflix.net/careers/job/{job_id_num}"
                jobs.append(NetflixJobListing(
                    title=name,
                    location=location.replace(",", ", "),
                    locations=[loc.replace(",", ", ") for loc in locations],
                    department=department,
                    business_unit=business_unit,
                    work_location_option=work_option,
                    job_id=ats_job_id,
                    job_url=job_url,
                ))
        else:
            # Fallback: extract from DOM (limited data available)
            job_cards = await page.query_selector_all(".position-card")
            
            for card in job_cards:
                try:
                    title_el = await card.query_selector(".position-title")
                    title = (await title_el.inner_text()).strip() if title_el else ""
                    
                    location_el = await card.query_selector(".position-location")
                    location = (await location_el.inner_text()).strip() if location_el else ""
                    
                    # Try to get department from card
                    dept_el = await card.query_selector("[id^='position-department']")
                    department = (await dept_el.inner_text()).strip() if dept_el else ""
                    
                    if title:
                        jobs.append(NetflixJobListing(
                            title=title,
                            location=location,
                            locations=[location] if location else [],
                            department=department,
                            business_unit="",
                            work_location_option="",
                            job_id="",
                            job_url="",
                        ))
                except Exception:
                    continue
        
        return jobs


BASE_URL = "https://explore.jobs.netflix.net/careers"


def build_search_url(
    query: str = "*",
    location: str | None = None,
    sort_by: str = "relevance",
) -> str:
    """Build a Netflix careers search URL with filters.
    
    Args:
        query: Search query (default "*" for all jobs)
        location: Location filter (e.g., "United Kingdom", "London")
        sort_by: Sort order (default "relevance")
        
    Returns:
        Full search URL with query parameters
    """
    from urllib.parse import urlencode, quote
    
    params = {
        "query": query,
        "sort_by": sort_by,
        "domain": "netflix.com",
    }
    
    if location:
        params["location"] = location
    
    return f"{BASE_URL}/search?{urlencode(params, quote_via=quote)}"


async def scrape_netflix_jobs(
    location: str | None = "United Kingdom",
    query: str = "*",
    headless: bool = True,
    save_to_db: bool = False,
    db_connection_string: str | None = None,
) -> list[NetflixJobListing]:
    """Scrape job listings from Netflix careers website.
    
    This is the primary function for retrieving Netflix job listings.
    It launches a headless browser, navigates to Netflix careers,
    applies filters, and extracts all matching job postings.
    
    Args:
        location: Location to filter jobs. Examples:
            - "United Kingdom" (default)
            - "London", "Madrid", "Amsterdam", "Los Angeles"
            - None to get all jobs worldwide
        query: Search query to filter jobs. Examples:
            - "*" (default) - all jobs
            - "engineer" - jobs containing "engineer"
            - "product manager" - jobs containing "product manager"
        headless: If True (default), runs browser without visible window.
            Set to False for debugging to see the browser.
        save_to_db: If True, saves jobs to database automatically
        db_connection_string: Database URL (required if save_to_db=True)
            Get from os.getenv("DATABASE_URL")
    
    Returns:
        List of NetflixJobListing objects, each containing:
            - title (str): Job title
            - location (str): Job location  
            - job_url (str): URL to apply/view details
        
        Returns empty list if no jobs found.
    
    Examples:
        >>> jobs = await scrape_netflix_jobs()  # UK jobs
        >>> jobs = await scrape_netflix_jobs(location="Madrid")
        >>> jobs = await scrape_netflix_jobs(location=None)  # worldwide
        >>> jobs = await scrape_netflix_jobs(query="engineer")
        
        >>> # Save to database automatically
        >>> jobs = await scrape_netflix_jobs(
        ...     location="United Kingdom",
        ...     save_to_db=True,
        ...     db_connection_string=os.getenv("DATABASE_URL")
        ... )
        
        >>> for job in jobs:
        ...     print(job.title)
    
    Note:
        - Requires Playwright and Chromium browser installed
        - Takes 5-15 seconds depending on number of results
        - Automatically scrolls to load all jobs (handles pagination)
    """
    url = build_search_url(query=query, location=location)
    
    from utils.logging import get_logger
    logger = get_logger(__name__)
    
    logger.info(f"🌐 Navigating to: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            logger.info("📡 Loading page...")
            # Use domcontentloaded instead of networkidle (much faster)
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
            logger.info("⏳ Waiting for job cards...")
            # Wait for job cards to appear
            try:
                await page.wait_for_selector(".position-card", timeout=10000)
                logger.info("✓ Job cards found")
            except:
                logger.warning("⚠️  No job cards found, proceeding anyway...")
            
            # Scroll to load all jobs (handles lazy loading/pagination)
            logger.info("📜 Scrolling to load all jobs...")
            await _scroll_to_load_all(page)
            
            # Create scraper and extract jobs
            logger.info("🔍 Extracting job data...")
            scraper = NetflixScraper()
            jobs = await scraper.scrape_job_search(url, page)
            logger.info(f"✅ Extracted {len(jobs)} jobs")
            
            # Save to database if requested
            if save_to_db:
                if not db_connection_string:
                    raise ValueError("db_connection_string required when save_to_db=True")
                
                logger.info("💾 Saving to database...")
                # Import here to avoid circular dependency
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent.parent.parent))
                from utils.db_client import save_jobs_to_db
                
                # Convert NetflixJobListing objects to dicts
                job_dicts = [
                    {
                        "title": job.title,
                        "job_url": job.job_url,
                        "location": job.location,
                        "department": job.department,
                        "business_unit": job.business_unit,
                        "work_type": job.work_location_option,
                        "job_id": job.job_id,
                    }
                    for job in jobs
                ]
                
                result = await save_jobs_to_db(
                    company_name="Netflix",
                    company_domain="netflix.com",
                    careers_url=BASE_URL,
                    jobs=job_dicts,
                    db_connection_string=db_connection_string
                )
                
                logger.info(f"✅ Database: {result['inserted']} inserted, {result['updated']} updated")
            
            return jobs
            
        finally:
            await browser.close()


async def _scroll_to_load_all(page: Page, max_scrolls: int = 10) -> None:
    """Scroll down the page to trigger lazy loading of all jobs.
    
    Netflix/Eightfold loads more jobs as you scroll, so we need to
    keep scrolling until no more jobs are loaded.
    """
    from utils.logging import get_logger
    logger = get_logger(__name__)
    
    previous_count = 0
    
    for i in range(max_scrolls):
        # Count current cards
        cards = await page.query_selector_all(".position-card")
        current_count = len(cards)
        
        if current_count > 0:
            logger.info(f"Loaded {current_count} jobs (scroll {i+1}/{max_scrolls})")
        
        # Scroll to bottom
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.5)  # Reduced from 1 second
        
        # Check if we've loaded more cards
        cards = await page.query_selector_all(".position-card")
        new_count = len(cards)
        
        if new_count == previous_count and new_count > 0:
            # No new cards loaded, we're done
            logger.info(f"✓ All jobs loaded ({new_count} total)")
            break
        previous_count = new_count
    
    # Scroll back to top
    await page.evaluate("window.scrollTo(0, 0)")


async def main():
    """Example usage of the Netflix scraper with database integration."""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Example 1: Just scrape jobs (no database)
    print("=== Scraping Netflix jobs (no database) ===")
    jobs = await scrape_netflix_jobs(location="United Kingdom")
    
    if jobs:
        print(f"\nFound {len(jobs)} Netflix job(s):\n")
        for i, job in enumerate(jobs[:5], 1):  # Show first 5
            print(f"{i}. {job.title}")
            print(f"   Department: {job.department}")
            print(f"   Location: {job.location}")
            print(f"   URL: {job.job_url}\n")
    else:
        print("No jobs found.")
    
    # Example 2: Scrape and save to database
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        print("\n=== Scraping and saving to database ===")
        jobs = await scrape_netflix_jobs(
            location="United Kingdom",
            save_to_db=True,
            db_connection_string=db_url
        )
        print(f"✅ Saved {len(jobs)} jobs to database")
    else:
        print("\n⚠️  DATABASE_URL not set - skipping database save")
    
    return jobs


if __name__ == "__main__":
    asyncio.run(main())
