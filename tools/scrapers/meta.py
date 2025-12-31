"""Meta Careers Scraper - Extract job listings from Meta's careers portal.

This module provides tools to scrape job listings from Meta's careers website
(metacareers.com), which uses a GraphQL API.

Primary Function:
    scrape_meta_jobs(location, query) -> list[MetaJobListing]
    
    This is the main function an agent should use to retrieve Meta job listings.

Example Usage:
    ```python
    import asyncio
    from tools.scrapers.meta import scrape_meta_jobs
    
    # Get all jobs in London, UK (default)
    jobs = asyncio.run(scrape_meta_jobs())
    
    # Get jobs in a specific location
    jobs = asyncio.run(scrape_meta_jobs(location="London, UK"))
    jobs = asyncio.run(scrape_meta_jobs(location="Madrid, Spain"))
    jobs = asyncio.run(scrape_meta_jobs(location="Amsterdam, Netherlands"))
    
    # Search for specific roles
    jobs = asyncio.run(scrape_meta_jobs(location="London, UK", query="engineer"))
    
    # Get all jobs worldwide (no location filter)
    jobs = asyncio.run(scrape_meta_jobs(location=None))
    
    # Access job data
    for job in jobs:
        print(f"Title: {job.title}")
        print(f"Location: {job.location}")
        print(f"URL: {job.job_url}")
    ```

Return Data Structure:
    Returns a list of MetaJobListing objects with:
    - title (str): Job title, e.g., "Software Engineer"
    - location (str): Primary job location, e.g., "London, UK"
    - locations (list[str]): All locations for this role
    - teams (list[str]): Team names, e.g., ["Software Engineering"]
    - sub_teams (list[str]): Sub-team names, e.g., ["Machine Learning"]
    - job_id (str): Meta job reference number
    - job_url (str): Direct URL to the job posting

Supported Locations (examples):
    - "London, UK", "Cambridge, UK", "Remote, UK"
    - "Dublin, Ireland", "Cork, Ireland"
    - "Amsterdam, Netherlands", "Paris, France"
    - "Berlin, Germany", "Munich, Germany"
    - "Madrid, Spain", "Stockholm, Sweden"
    - Or any location listed on Meta careers

Notes:
    - This function uses Playwright for browser automation (headless by default)
    - The scraper intercepts GraphQL responses to extract job data
    - Network requests may take 5-15 seconds depending on result count
"""

import asyncio
from dataclasses import dataclass
import sys
from pathlib import Path
from urllib.parse import quote

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
class MetaJobListing:
    """A job listing from Meta search results.
    
    Attributes:
        title: The job title (e.g., "Software Engineer")
        location: Primary job location (e.g., "London, UK")
        locations: All locations for this role (list, for multi-location jobs)
        teams: Team names (e.g., ["Software Engineering", "AI Research"])
        sub_teams: Sub-team names (e.g., ["Machine Learning", "Computer Vision"])
        job_id: Meta job reference number (e.g., "5227205160837020")
        job_url: Direct URL to the job posting on Meta careers
    """
    title: str
    location: str
    locations: list[str]
    teams: list[str]
    sub_teams: list[str]
    job_id: str
    job_url: str


@dataclass
class MetaJobDetails:
    """Full details of a Meta job posting from the job detail page.
    
    Attributes:
        title: Job title
        location: Primary job location
        teams: Team/department name
        job_id: Meta job reference number
        job_description: Full job description blob (description + responsibilities + qualifications)
        job_url: URL of the job detail page
        apply_url: URL to the application form
    """
    title: str
    location: str
    teams: str
    job_id: str
    job_description: str
    job_url: str
    apply_url: str


class MetaScraper(BaseScraper):
    """Scraper for Meta careers pages (GraphQL-based)."""
    
    URL_PATTERNS = ["metacareers.com", "facebook.com/careers"]
    
    async def scrape_job_listing(self, url: str, page: Page) -> ScrapedJob:
        """Extract job data from a Meta job detail page."""
        
        # Wait for content to load
        try:
            await page.wait_for_selector('[data-testid="job-title"]', timeout=10000)
        except Exception:
            pass
        
        # Try different selectors for job details
        title = await self.extract_text(page, 'h1')
        location = await self.extract_text(page, '[data-testid="job-location"]')
        description = await self.extract_text(page, '[data-testid="job-description"]')
        
        # Fallback selectors
        if not title:
            title = await self.extract_text(page, '[class*="title"]')
        if not description:
            description = await self.extract_text(page, '[class*="description"]')
        
        return ScrapedJob(
            company="Meta",
            role=title,
            location=location,
            description=description,
            responsibilities=[],
            qualifications=[],
        )
    
    async def scrape_job_search(self, url: str, page: Page) -> list[MetaJobListing]:
        """Scrape all job listings from Meta search results page.
        
        This method should be called with a page that has already intercepted
        the GraphQL responses. Use scrape_meta_jobs() instead for the full flow.
        
        Args:
            url: Meta careers search URL
            page: Playwright page object (already navigated to URL)
            
        Returns:
            List of job listings with title, location, and URL
        """
        # This method is here for interface consistency, but the actual
        # scraping is done via GraphQL interception in scrape_meta_jobs()
        return []


BASE_URL = "https://www.metacareers.com/jobs"


def build_search_url(
    query: str | None = None,
    location: str | None = None,
) -> str:
    """Build a Meta careers search URL with filters.
    
    Args:
        query: Search query (e.g., "engineer", "product manager")
        location: Location filter (e.g., "London, UK", "Amsterdam, Netherlands")
        
    Returns:
        Full search URL with query parameters
    """
    params = []
    
    if query:
        params.append(f"q={quote(query)}")
    
    if location:
        params.append(f"offices[0]={quote(location)}")
    
    if params:
        return f"{BASE_URL}?{'&'.join(params)}"
    return BASE_URL


async def scrape_meta_jobs(
    location: str | None = "London, UK",
    query: str | None = None,
    headless: bool = True,
    save_to_db: bool = False,
    db_connection_string: str | None = None,
) -> list[MetaJobListing]:
    """Scrape job listings from Meta careers website.
    
    This is the primary function for retrieving Meta job listings.
    It launches a headless browser, navigates to Meta careers,
    applies filters, and extracts all matching job postings via GraphQL.
    
    Args:
        location: Location to filter jobs. Examples:
            - "London, UK" (default)
            - "Dublin, Ireland", "Amsterdam, Netherlands", "Paris, France"
            - "Berlin, Germany", "Madrid, Spain", "Remote, UK"
            - None to get all jobs worldwide
        query: Search query to filter jobs. Examples:
            - None (default) - all jobs
            - "engineer" - jobs containing "engineer"
            - "product manager" - jobs containing "product manager"
        headless: If True (default), runs browser without visible window.
            Set to False for debugging to see the browser.
        save_to_db: If True, saves jobs to database automatically
        db_connection_string: Database URL (required if save_to_db=True)
            Get from os.getenv("DATABASE_URL")
    
    Returns:
        List of MetaJobListing objects, each containing:
            - title (str): Job title
            - location (str): Primary job location  
            - locations (list[str]): All locations for this role
            - teams (list[str]): Team names
            - sub_teams (list[str]): Sub-team names
            - job_id (str): Meta job ID
            - job_url (str): URL to apply/view details
        
        Returns empty list if no jobs found.
    
    Examples:
        >>> jobs = await scrape_meta_jobs()  # London, UK jobs
        >>> jobs = await scrape_meta_jobs(location="Dublin, Ireland")
        >>> jobs = await scrape_meta_jobs(location=None)  # worldwide
        >>> jobs = await scrape_meta_jobs(query="engineer")
        >>> jobs = await scrape_meta_jobs(location="London, UK", query="engineer")
        
        >>> # Save to database automatically
        >>> jobs = await scrape_meta_jobs(
        ...     location="London, UK",
        ...     save_to_db=True,
        ...     db_connection_string=os.getenv("DATABASE_URL")
        ... )
        
        >>> for job in jobs:
        ...     print(job.title)
    
    Note:
        - Requires Playwright and Chromium browser installed
        - Takes 5-15 seconds depending on number of results
        - Uses GraphQL API interception for reliable data extraction
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
        
        jobs: list[MetaJobListing] = []
        
        async def handle_response(response):
            """Intercept GraphQL responses containing job data."""
            if "graphql" not in response.url.lower():
                return
            
            try:
                body = await response.json()
                if "data" not in body:
                    return
                    
                data = body["data"]
                
                # Handle job search results
                if "job_search_with_featured_jobs" in data:
                    all_jobs = data["job_search_with_featured_jobs"].get("all_jobs", [])
                    logger.info(f"📡 Intercepted {len(all_jobs)} jobs from GraphQL")
                    for job in all_jobs:
                        job_id = job.get("id", "")
                        locations_list = job.get("locations", [])
                        
                        jobs.append(MetaJobListing(
                            title=job.get("title", "").strip(),
                            location=locations_list[0] if locations_list else "",
                            locations=locations_list,
                            teams=job.get("teams", []),
                            sub_teams=job.get("sub_teams", []),
                            job_id=job_id,
                            job_url=f"https://www.metacareers.com/jobs/{job_id}" if job_id else "",
                        ))
            except Exception:
                pass
        
        page.on("response", handle_response)
        
        try:
            logger.info("📡 Loading page...")
            # Use domcontentloaded instead of networkidle (much faster)
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
            # Accept cookies if consent dialog appears
            logger.info("🍪 Checking for cookie consent...")
            await _accept_cookies(page)
            
            # Wait for initial content and GraphQL responses
            logger.info("⏳ Waiting for GraphQL responses...")
            await asyncio.sleep(3)
            
            # Scroll to trigger any lazy loading
            logger.info("📜 Scrolling to load all jobs...")
            await _scroll_to_load_all(page, logger)
            
            logger.info(f"✅ Extracted {len(jobs)} jobs")
            
            # Save to database if requested
            if save_to_db:
                if not db_connection_string:
                    raise ValueError("db_connection_string required when save_to_db=True")
                
                logger.info("💾 Saving to database...")
                # Import here to avoid circular dependency
                from utils.db_client import save_jobs_to_db
                
                # Convert MetaJobListing objects to dicts
                job_dicts = [
                    {
                        "title": job.title,
                        "job_url": job.job_url,
                        "location": job.location,
                        "department": ", ".join(job.teams) if job.teams else "",
                        "business_unit": ", ".join(job.sub_teams) if job.sub_teams else "",
                        "work_type": "",
                        "job_id": job.job_id,
                    }
                    for job in jobs
                ]
                
                result = await save_jobs_to_db(
                    company_name="Meta",
                    company_domain="metacareers.com",
                    careers_url=BASE_URL,
                    jobs=job_dicts,
                    db_connection_string=db_connection_string
                )
                
                logger.info(f"✅ Database: {result['inserted']} inserted, {result['updated']} updated")
            
            return jobs
            
        finally:
            await browser.close()


async def get_meta_locations(headless: bool = True) -> list[dict]:
    """Get all available location filters from Meta careers.
    
    Returns:
        List of location dictionaries with keys:
            - id (str): Location identifier (e.g., "london")
            - location_display_name (str): Display name (e.g., "London, UK")
            - country (str): Country name (e.g., "UK")
            - is_remote (bool): Whether it's a remote position
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        locations: list[dict] = []
        
        async def handle_response(response):
            if "graphql" not in response.url.lower():
                return
            try:
                body = await response.json()
                if "data" in body and "job_search_filters" in body["data"]:
                    filters = body["data"]["job_search_filters"]
                    if "locations" in filters:
                        locations.extend(filters["locations"])
            except Exception:
                pass
        
        page.on("response", handle_response)
        
        try:
            await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            return locations
        finally:
            await browser.close()


async def get_meta_teams(headless: bool = True) -> list[str]:
    """Get all available team filters from Meta careers.
    
    Returns:
        List of team names (e.g., ["Software Engineering", "AI Research", ...])
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        teams: list[str] = []
        
        async def handle_response(response):
            if "graphql" not in response.url.lower():
                return
            try:
                body = await response.json()
                if "data" in body and "job_search_filters" in body["data"]:
                    filters = body["data"]["job_search_filters"]
                    if "teams" in filters:
                        for team in filters["teams"]:
                            team_name = team.get("team_display_name")
                            if team_name:
                                teams.append(team_name)
            except Exception:
                pass
        
        page.on("response", handle_response)
        
        try:
            await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            return teams
        finally:
            await browser.close()


async def _accept_cookies(page: Page) -> None:
    """Accept cookie consent dialog if present."""
    try:
        accept_btn = await page.query_selector('button:has-text("Accept All")')
        if accept_btn:
            await accept_btn.click()
            await asyncio.sleep(1)
    except Exception:
        pass


async def _scroll_to_load_all(page: Page, logger=None, max_scrolls: int = 10) -> None:
    """Scroll down the page to trigger lazy loading of all jobs.
    
    Meta loads jobs via GraphQL, so scrolling helps ensure all data is fetched.
    """
    for i in range(max_scrolls):
        await page.evaluate(f"window.scrollTo(0, {(i + 1) * 1000})")
        await asyncio.sleep(0.3)
        if logger:
            logger.debug(f"Scroll {i+1}/{max_scrolls}")
    
    # Scroll back to top
    await page.evaluate("window.scrollTo(0, 0)")


async def scrape_meta_job_details(job_url: str, headless: bool = True) -> MetaJobDetails:
    """Scrape full details from a Meta job detail page.
    
    Args:
        job_url: URL to the Meta job detail page
        headless: Run browser in headless mode
    
    Returns:
        MetaJobDetails with all job information
    """
    from utils.logging import get_logger
    logger = get_logger(__name__)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        
        logger.info(f"Fetching job details from: {job_url}")
        await page.goto(job_url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        
        # Accept cookies if present
        try:
            cookie_btn = await page.query_selector('button[data-cookiebanner="accept_button"]')
            if cookie_btn:
                await cookie_btn.click()
                await page.wait_for_timeout(1000)
        except:
            pass
        
        result = {}
        
        # Get body text
        body_text = await page.inner_text("body")
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
        
        # Title - first occurrence that's not a nav item
        for line in lines:
            if line not in ["Jobs", "Teams", "Career Programs", "Working at Meta", "Blog", "Skip to main content"]:
                result["title"] = line
                break
        
        # Location - look for location pattern after title
        result["location"] = ""
        for i, line in enumerate(lines):
            if line == result.get("title", "") and i + 1 < len(lines):
                # Next non-title line should be location
                for j in range(i + 1, min(i + 5, len(lines))):
                    if lines[j] != result["title"] and not lines[j].startswith("+"):
                        result["location"] = lines[j]
                        break
                break
        
        # Teams - look for team name after location
        result["teams"] = ""
        for i, line in enumerate(lines):
            if line == result.get("location", "") and i + 1 < len(lines):
                result["teams"] = lines[i + 1]
                break
        
        # Job ID from URL
        result["job_id"] = job_url.split("/")[-1] if "/" in job_url else ""
        
        # Build job_description from body text
        # Find sections: responsibilities, qualifications
        full_text = "\n".join(lines)
        
        resp_markers = ["Responsibilities", "What you'll do", "Your role"]
        qual_markers = ["Minimum Qualifications", "Qualifications", "Requirements", "What we're looking for"]
        about_markers = ["About Meta", "Equal Employment"]
        
        resp_idx = -1
        for marker in resp_markers:
            idx = full_text.find(marker)
            if idx > 0:
                resp_idx = idx
                break
        
        qual_idx = -1
        for marker in qual_markers:
            idx = full_text.find(marker)
            if idx > 0:
                qual_idx = idx
                break
        
        about_idx = -1
        for marker in about_markers:
            idx = full_text.find(marker)
            if idx > 0:
                about_idx = idx
                break
        
        # Description - from Apply button text to responsibilities
        apply_idx = full_text.find("Apply now")
        if apply_idx > 0 and resp_idx > apply_idx:
            desc_start = apply_idx + len("Apply now")
            description = full_text[desc_start:resp_idx].strip()
        else:
            description = ""
        
        # Responsibilities - from resp_idx to qual_idx
        responsibilities = ""
        if resp_idx > 0 and qual_idx > resp_idx:
            responsibilities = full_text[resp_idx:qual_idx].strip()
        elif resp_idx > 0 and about_idx > resp_idx:
            responsibilities = full_text[resp_idx:about_idx].strip()
        
        # Qualifications - from qual_idx to about_idx
        qualifications = ""
        if qual_idx > 0 and about_idx > qual_idx:
            qualifications = full_text[qual_idx:about_idx].strip()
        elif qual_idx > 0:
            qualifications = full_text[qual_idx:qual_idx+2000].strip()
        
        # Combine into job_description blob
        parts = []
        if description:
            parts.append(description)
        if responsibilities:
            parts.append(f"\n\n{responsibilities}")
        if qualifications:
            parts.append(f"\n\n{qualifications}")
        result["job_description"] = "".join(parts)
        
        result["job_url"] = job_url
        result["apply_url"] = job_url  # Meta uses same page for viewing and applying
        
        await browser.close()
        
        logger.info(f"Extracted details for: {result.get('title', 'Unknown')}")
        return MetaJobDetails(**result)


async def main():
    """Example usage of the Meta scraper with database integration."""
    import os
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use environment variables directly
    
    # Example 1: Just scrape jobs (no database)
    print("=== Scraping Meta jobs (no database) ===")
    jobs = await scrape_meta_jobs(location="London, UK")
    
    if jobs:
        print(f"\nFound {len(jobs)} Meta job(s):\n")
        for i, job in enumerate(jobs[:5], 1):  # Show first 5
            print(f"{i}. {job.title}")
            print(f"   Teams: {', '.join(job.teams) if job.teams else 'N/A'}")
            print(f"   Location: {job.location}")
            print(f"   URL: {job.job_url}\n")
    else:
        print("No jobs found.")
    
    # Example 2: Scrape and save to database
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        print("\n=== Scraping and saving to database ===")
        jobs = await scrape_meta_jobs(
            location="London, UK",
            save_to_db=True,
            db_connection_string=db_url
        )
        print(f"✅ Saved {len(jobs)} jobs to database")
    else:
        print("\n⚠️  DATABASE_URL not set - skipping database save")
    
    return jobs


if __name__ == "__main__":
    asyncio.run(main())
