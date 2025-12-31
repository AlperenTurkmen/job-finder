"""Google Careers Scraper - Extract job listings from Google's careers portal.

This module provides tools to scrape job listings from Google's careers website
(google.com/about/careers/applications/jobs/results).

Primary Function:
    scrape_google_jobs(location, query, headless, save_to_db, db_connection_string) -> list[GoogleJobListing]
    
    This is the main function an agent should use to retrieve Google job listings.

Example Usage:
    ```python
    import asyncio
    from tools.scrapers.google import scrape_google_jobs
    
    # Get jobs in London (default)
    jobs = asyncio.run(scrape_google_jobs())
    
    # Get jobs in a specific location
    jobs = asyncio.run(scrape_google_jobs(location="London"))
    jobs = asyncio.run(scrape_google_jobs(location="New York"))
    jobs = asyncio.run(scrape_google_jobs(location="Singapore"))
    
    # Search for specific roles
    jobs = asyncio.run(scrape_google_jobs(query="software engineer"))
    jobs = asyncio.run(scrape_google_jobs(query="product manager"))
    
    # Get all jobs worldwide (no location filter)
    jobs = asyncio.run(scrape_google_jobs(location=None))
    
    # Limit pages scraped
    jobs = asyncio.run(scrape_google_jobs(location="London", max_pages=2))
    
    # Save to database
    jobs = asyncio.run(scrape_google_jobs(
        save_to_db=True,
        db_connection_string="postgresql://user:pass@localhost/db"
    ))
    
    # Access job data
    for job in jobs:
        print(f"Title: {job.title}")
        print(f"Location: {job.location}")
        print(f"Level: {job.level}")
        print(f"URL: {job.job_url}")
    ```

Return Data Structure:
    Returns a list of GoogleJobListing objects with:
    - title (str): Job title, e.g., "Senior Software Engineer, AI"
    - location (str): Job location, e.g., "London, UK"
    - level (str): Experience level, e.g., "Mid", "Senior", "Advanced"
    - remote_eligible (bool): Whether remote work is available
    - company (str): Company name (usually "Google")
    - job_id (str): Google job ID
    - job_url (str): Direct URL to the job posting

Notes:
    - Uses Playwright to scrape paginated results
    - Default pagination shows 20 jobs per page
    - Total job count can exceed 2000+
    - Location filtering uses Google's search parameter
"""

import asyncio
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page

load_dotenv()

try:
    from utils.logging import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

try:
    from tools.scrapers.base import BaseScraper, ScrapedJob
except ImportError:
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
class GoogleJobListing:
    """A job listing from Google careers search results.
    
    Attributes:
        title: The job title (e.g., "Senior Software Engineer, AI")
        location: Job location (e.g., "London, UK")
        level: Experience level (e.g., "Mid", "Senior", "Advanced")
        remote_eligible: Whether remote work is available
        company: Company name (usually "Google")
        job_id: Google job ID
        job_url: Direct URL to the job posting
    """
    title: str
    location: str
    level: str
    remote_eligible: bool
    company: str
    job_id: str
    job_url: str


@dataclass
class GoogleJobDetails:
    """Full details of a Google job posting.
    
    Attributes:
        title: Job title
        location: Job location
        level: Experience level
        job_id: Google job ID
        job_description: Full job description blob
        job_url: URL of the job detail page
        apply_url: URL to the application form
    """
    title: str
    location: str
    level: str
    job_id: str
    job_description: str
    job_url: str
    apply_url: str


class GoogleScraper(BaseScraper):
    """Scraper for Google careers pages."""
    
    URL_PATTERNS = ["google.com/about/careers", "careers.google.com"]
    
    async def scrape_job_listing(self, url: str, page: Page) -> ScrapedJob:
        """Extract job data from a Google job detail page."""
        
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        title = await self.extract_text(page, "h1")
        location = await self.extract_text(page, "[data-field='location']")
        description = await self.extract_text(page, "[data-field='description']")
        
        return ScrapedJob(
            company="Google",
            role=title,
            location=location,
            description=description,
            responsibilities=[],
            qualifications=[],
        )


# URLs
BASE_URL = "https://www.google.com/about/careers/applications"
SEARCH_URL = "https://www.google.com/about/careers/applications/jobs/results"
JOBS_PER_PAGE = 20


def _parse_job_from_item(text: str, job_id: str) -> Optional[GoogleJobListing]:
    """Parse a job listing from list item text."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    if not lines or lines[0] in ['Learn more', 'share', 'Google']:
        return None
    
    title = lines[0]
    
    # Find location (after 'place')
    location = ''
    for i, line in enumerate(lines):
        if line == 'place' and i + 1 < len(lines):
            location = lines[i + 1]
            break
    
    # Find level (after 'bar_chart')
    level = ''
    for i, line in enumerate(lines):
        if line == 'bar_chart' and i + 1 < len(lines):
            level = lines[i + 1]
            break
    
    # Check for remote
    remote_eligible = 'laptop_windows' in text or 'Remote eligible' in text
    
    # Find company (after 'corporate_fare')
    company = 'Google'
    for i, line in enumerate(lines):
        if line == 'corporate_fare' and i + 1 < len(lines):
            company = lines[i + 1]
            break
    
    job_url = f"{SEARCH_URL}/{job_id}" if job_id else ""
    
    return GoogleJobListing(
        title=title,
        location=location,
        level=level,
        remote_eligible=remote_eligible,
        company=company,
        job_id=job_id,
        job_url=job_url
    )


async def _scrape_page(page: Page, url: str) -> tuple[list[GoogleJobListing], int]:
    """Scrape a single page of job listings.
    
    Returns:
        Tuple of (jobs list, total job count)
    """
    await page.goto(url, timeout=60000, wait_until='networkidle')
    await asyncio.sleep(3)
    
    # Get total count
    body = await page.inner_text('body')
    count_match = re.search(r'([\d,]+)\s*jobs?\s*matched', body)
    total_count = int(count_match.group(1).replace(',', '')) if count_match else 0
    
    # Get job IDs from HTML
    content = await page.content()
    job_ids = re.findall(r'/results/(\d+)', content)
    # Remove duplicates while preserving order
    seen = set()
    unique_job_ids = []
    for jid in job_ids:
        if jid not in seen:
            seen.add(jid)
            unique_job_ids.append(jid)
    
    # Parse job items
    items = await page.query_selector_all('li')
    jobs = []
    job_idx = 0
    
    for item in items:
        text = (await item.inner_text()).strip()
        if 'Learn more' in text and 'place' in text:
            job_id = unique_job_ids[job_idx] if job_idx < len(unique_job_ids) else ''
            job = _parse_job_from_item(text, job_id)
            if job:
                jobs.append(job)
                job_idx += 1
    
    return jobs, total_count


async def scrape_google_jobs(
    location: Optional[str] = "London",
    query: Optional[str] = "",
    headless: bool = True,
    save_to_db: bool = False,
    db_connection_string: Optional[str] = None,
    max_pages: int = 10,
) -> list[GoogleJobListing]:
    """Scrape job listings from Google careers.
    
    Args:
        location: Location to filter jobs by (e.g., "London", "New York").
                  Set to None or empty string for all locations.
        query: Search term to filter jobs (e.g., "software engineer").
               Set to empty string for all jobs.
        headless: Whether to run browser in headless mode (default True).
        save_to_db: Whether to save results to a database (default False).
        db_connection_string: Database connection string. If not provided,
                              uses DATABASE_URL environment variable.
        max_pages: Maximum number of pages to scrape (default 10).
                   Each page has ~20 jobs.
    
    Returns:
        List of GoogleJobListing objects matching the search criteria.
    
    Example:
        # Get London engineering jobs
        jobs = await scrape_google_jobs(location="London", query="engineer")
        
        # Get all jobs in Singapore
        jobs = await scrape_google_jobs(location="Singapore")
        
        # Get all jobs worldwide (limited to first 5 pages)
        jobs = await scrape_google_jobs(location=None, max_pages=5)
    """
    logger.info(f"Starting Google job scrape - location: {location}, query: {query}")
    
    jobs: list[GoogleJobListing] = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Build URL with filters
            params = []
            if location:
                params.append(f"location={quote(location)}")
            if query:
                params.append(f"q={quote(query)}")
            
            base_url = SEARCH_URL
            if params:
                base_url = f"{SEARCH_URL}?{'&'.join(params)}"
            
            # Scrape first page to get total count
            page_jobs, total_count = await _scrape_page(page, base_url)
            jobs.extend(page_jobs)
            logger.info(f"Total jobs available: {total_count}")
            logger.info(f"Page 1: {len(page_jobs)} jobs")
            
            # Calculate pages needed
            total_pages = (total_count + JOBS_PER_PAGE - 1) // JOBS_PER_PAGE
            pages_to_scrape = min(total_pages, max_pages)
            
            # Scrape remaining pages
            for page_num in range(2, pages_to_scrape + 1):
                page_url = f"{base_url}{'&' if params else '?'}page={page_num}"
                page_jobs, _ = await _scrape_page(page, page_url)
                jobs.extend(page_jobs)
                logger.info(f"Page {page_num}: {len(page_jobs)} jobs")
            
            logger.info(f"Scraped {len(jobs)} jobs from Google")
            
        finally:
            await browser.close()
    
    # Save to database if requested
    if save_to_db:
        conn_string = db_connection_string or os.getenv("DATABASE_URL")
        if conn_string:
            await _save_to_database(jobs, conn_string)
        else:
            logger.warning("save_to_db=True but no database connection string provided")
    
    return jobs


async def _save_to_database(jobs: list[GoogleJobListing], connection_string: str) -> None:
    """Save job listings to database."""
    logger.info(f"Saving {len(jobs)} jobs to database")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(connection_string)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS google_jobs (
                job_id VARCHAR(50) PRIMARY KEY,
                title VARCHAR(500),
                location VARCHAR(200),
                level VARCHAR(50),
                remote_eligible BOOLEAN,
                company VARCHAR(100),
                job_url VARCHAR(500),
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        for job in jobs:
            await conn.execute("""
                INSERT INTO google_jobs 
                (job_id, title, location, level, remote_eligible, company, job_url)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (job_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    location = EXCLUDED.location,
                    level = EXCLUDED.level,
                    remote_eligible = EXCLUDED.remote_eligible,
                    scraped_at = CURRENT_TIMESTAMP
            """, job.job_id, job.title, job.location, job.level,
                job.remote_eligible, job.company, job.job_url)
        
        await conn.close()
        logger.info(f"Successfully saved {len(jobs)} jobs to database")
        
    except ImportError:
        logger.error("asyncpg not installed. Run: pip install asyncpg")
    except Exception as e:
        logger.error(f"Failed to save to database: {e}")


async def scrape_google_job_details(job_url: str, headless: bool = True) -> GoogleJobDetails:
    """Scrape full details from a Google job detail page.
    
    Note: Google careers shows job details in a side panel. The function 
    extracts job details by finding the job in the list and parsing the 
    inline details shown.
    
    Args:
        job_url: URL to the Google job detail page (can include job ID in URL)
        headless: Run browser in headless mode
    
    Returns:
        GoogleJobDetails with all job information
    """
    import re
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        
        logger.info(f"Fetching job details from: {job_url}")
        await page.goto(job_url, wait_until="load", timeout=60000)
        await page.wait_for_timeout(4000)  # Google pages are JavaScript heavy
        
        # Accept cookies if present
        try:
            agree_btn = await page.query_selector('button:has-text("Agree")')
            if agree_btn:
                await agree_btn.click()
                await page.wait_for_timeout(2000)
        except:
            pass
        
        result = {}
        
        # Get body text
        body_text = await page.inner_text("body")
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
        
        # Extract job_id from URL
        job_id_match = re.search(r'/results/(\d+)', job_url)
        result["job_id"] = job_id_match.group(1) if job_id_match else ""
        
        # Find the job details section - look for "Jobs search results" marker
        # then find job info after that
        full_text = "\n".join(lines)
        
        # Title - look for title in the content (after "Jobs search results")
        result["title"] = ""
        search_results_idx = None
        for i, line in enumerate(lines):
            if line == "Jobs search results":
                search_results_idx = i
                break
        
        if search_results_idx and search_results_idx + 1 < len(lines):
            # First job title is usually right after
            for line in lines[search_results_idx + 1:search_results_idx + 5]:
                if line and line not in ["corporate_fare", "Google", "place"] and len(line) > 10:
                    result["title"] = line
                    break
        
        # Location - find after "place" marker
        result["location"] = ""
        for i, line in enumerate(lines):
            if line == "place" and i + 1 < len(lines):
                result["location"] = lines[i + 1]
                break
        
        # Level - find after "bar_chart" marker
        result["level"] = ""
        for i, line in enumerate(lines):
            if line == "bar_chart" and i + 1 < len(lines):
                result["level"] = lines[i + 1]
                break
        
        # Build job_description from body text
        # Google shows "Minimum qualifications" inline after the job info
        min_qual_idx = full_text.find("Minimum qualifications")
        pref_qual_idx = full_text.find("Preferred qualifications")
        about_idx = full_text.find("About the job")
        resp_idx = full_text.find("Responsibilities")
        
        parts = []
        
        # About the job section
        if about_idx >= 0:
            end_idx = resp_idx if resp_idx > about_idx else (min_qual_idx if min_qual_idx > about_idx else len(full_text))
            parts.append(full_text[about_idx:end_idx].strip())
        
        # Responsibilities section
        if resp_idx >= 0:
            end_idx = min_qual_idx if min_qual_idx > resp_idx else len(full_text)
            parts.append(f"\n\n{full_text[resp_idx:end_idx].strip()}")
        
        # Minimum qualifications section
        if min_qual_idx >= 0:
            end_idx = pref_qual_idx if pref_qual_idx > min_qual_idx else len(full_text)
            parts.append(f"\n\n{full_text[min_qual_idx:end_idx].strip()}")
        
        # Preferred qualifications section
        if pref_qual_idx >= 0:
            # Find end - usually "Learn more" or another job listing
            learn_more_idx = full_text.find("Learn more", pref_qual_idx)
            end_idx = learn_more_idx if learn_more_idx > pref_qual_idx else len(full_text)
            parts.append(f"\n\n{full_text[pref_qual_idx:end_idx].strip()}")
        
        result["job_description"] = "".join(parts) if parts else full_text[:3000]
        
        result["job_url"] = job_url
        result["apply_url"] = job_url  # Google uses same page for apply
        
        await browser.close()
        
        logger.info(f"Extracted details for: {result['title']}")
        return GoogleJobDetails(**result)
        logger.info(f"Extracted details for: {result['title']}")
        return GoogleJobDetails(**result)


async def main():
    """Test the scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape Google job listings")
    parser.add_argument("--location", default="London", help="Location to filter by")
    parser.add_argument("--query", default="", help="Search query")
    parser.add_argument("--max-pages", type=int, default=3, help="Max pages to scrape")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", dest="headless", action="store_false")
    parser.add_argument("--save-to-db", action="store_true")
    parser.add_argument("--db-connection-string", help="Database connection string")
    parser.add_argument("--worldwide", action="store_true", help="Get all jobs worldwide")
    
    args = parser.parse_args()
    
    location = None if args.worldwide else args.location
    
    jobs = await scrape_google_jobs(
        location=location,
        query=args.query,
        headless=args.headless,
        save_to_db=args.save_to_db,
        db_connection_string=args.db_connection_string,
        max_pages=args.max_pages,
    )
    
    print(f"\nFound {len(jobs)} jobs")
    print("=" * 70)
    
    for job in jobs[:10]:
        print(f"\nTitle: {job.title}")
        print(f"Location: {job.location}")
        print(f"Level: {job.level}")
        print(f"Remote: {job.remote_eligible}")
        print(f"URL: {job.job_url}")
        print("-" * 50)
    
    if len(jobs) > 10:
        print(f"\n... and {len(jobs) - 10} more jobs")


if __name__ == "__main__":
    asyncio.run(main())
