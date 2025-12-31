"""Miniclip Careers Scraper - Extract job listings from Miniclip's careers portal.

This module provides tools to scrape job listings from Miniclip's careers website
(careers.miniclip.com), which uses Jobs2Web ATS.

Primary Function:
    scrape_miniclip_jobs(location, query, headless, save_to_db, db_connection_string) -> list[MiniclipJobListing]
    
    This is the main function an agent should use to retrieve Miniclip job listings.

Example Usage:
    ```python
    import asyncio
    from tools.scrapers.miniclip import scrape_miniclip_jobs
    
    # Get all jobs in United Kingdom (default)
    jobs = asyncio.run(scrape_miniclip_jobs())
    
    # Get jobs in a specific location
    jobs = asyncio.run(scrape_miniclip_jobs(location="London"))
    jobs = asyncio.run(scrape_miniclip_jobs(location="Zoetermeer"))
    jobs = asyncio.run(scrape_miniclip_jobs(location="Lisbon"))
    
    # Search for specific roles
    jobs = asyncio.run(scrape_miniclip_jobs(query="developer"))
    jobs = asyncio.run(scrape_miniclip_jobs(query="engineer"))
    
    # Get all jobs worldwide (no location filter)
    jobs = asyncio.run(scrape_miniclip_jobs(location=None))
    
    # Save to database
    jobs = asyncio.run(scrape_miniclip_jobs(
        save_to_db=True,
        db_connection_string="postgresql://user:pass@localhost/db"
    ))
    
    # Access job data
    for job in jobs:
        print(f"Title: {job.title}")
        print(f"Location: {job.location}")
        print(f"URL: {job.job_url}")
    ```

Return Data Structure:
    Returns a list of MiniclipJobListing objects with:
    - title (str): Job title, e.g., "Senior Backend Developer"
    - location (str): Job location, e.g., "London, GB", "Zoetermeer, NL"
    - city (str): City extracted from location, e.g., "London"
    - country_code (str): Country code, e.g., "GB", "NL", "PT"
    - posted_date (str): When the job was posted, e.g., "28 Dec 2025"
    - job_url (str): Direct URL to the job posting

Supported Locations:
    - "London" / "GB" / "United Kingdom" - London office
    - "Zoetermeer" / "NL" / "Netherlands" - Netherlands office
    - "Lisbon" / "PT" / "Portugal" - Portugal office
    - "Nottingham" / "Derby" - UK regional offices
    - "Izmir" / "TR" / "Turkey" - Turkey office
    - None - All locations worldwide

Notes:
    - This function uses Playwright to scrape the careers search page
    - All jobs are returned from a single page (no pagination needed)
    - Location filtering is done client-side after fetching
"""

import asyncio
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
class MiniclipJobListing:
    """A job listing from Miniclip search results.
    
    Attributes:
        title: The job title (e.g., "Senior Backend Developer")
        location: Full location string (e.g., "London, GB")
        city: City name (e.g., "London")
        country_code: Two-letter country code (e.g., "GB", "NL", "PT")
        posted_date: When the job was posted (e.g., "28 Dec 2025")
        job_url: Direct URL to the job posting
    """
    title: str
    location: str
    city: str
    country_code: str
    posted_date: str
    job_url: str


@dataclass
class MiniclipJobDetails:
    """Full details of a Miniclip job posting.
    
    Attributes:
        title: Job title
        location: Job location
        department: Department name
        job_id: Miniclip job ID
        job_description: Full job description blob
        job_url: URL of the job detail page
        apply_url: URL to the application form
    """
    title: str
    location: str
    department: str
    job_id: str
    job_description: str
    job_url: str
    apply_url: str


class MiniclipScraper(BaseScraper):
    """Scraper for Miniclip careers pages."""
    
    URL_PATTERNS = ["careers.miniclip.com", "miniclip.com/careers"]
    
    async def scrape_job_listing(self, url: str, page: Page) -> ScrapedJob:
        """Extract job data from a Miniclip job detail page."""
        
        await page.wait_for_load_state("load")
        await asyncio.sleep(2)
        
        body = await page.inner_text("body")
        
        # Extract title
        title_match = re.search(r'^([^\n]+)', body.split("Apply now")[0].split("Job Description")[0])
        title = title_match.group(1).strip() if title_match else ""
        
        # Extract location
        loc_match = re.search(r'Location:\s*([^\n]+)', body)
        location = loc_match.group(1).strip() if loc_match else ""
        
        # Extract description
        desc_match = re.search(r'Job Description\s*(.*?)(?:Requirements|Qualifications|What we)', body, re.DOTALL)
        description = desc_match.group(1).strip() if desc_match else ""
        
        return ScrapedJob(
            company="Miniclip",
            role=title,
            location=location,
            description=description,
            responsibilities=[],
            qualifications=[],
        )


# URLs
BASE_URL = "https://careers.miniclip.com"
SEARCH_URL = "https://careers.miniclip.com/search/?q=&sortColumn=referencedate&sortDirection=desc"

# Location mappings
COUNTRY_MAPPINGS = {
    "united kingdom": ["GB"],
    "uk": ["GB"],
    "netherlands": ["NL"],
    "holland": ["NL"],
    "portugal": ["PT"],
    "turkey": ["TR"],
}


def _parse_location(location_str: str) -> tuple[str, str]:
    """Parse location string into city and country code."""
    parts = location_str.split(",")
    if len(parts) >= 2:
        city = parts[0].strip()
        country_code = parts[-1].strip()
        return city, country_code
    return location_str, ""


def _parse_job(row_data: dict) -> MiniclipJobListing:
    """Parse a job from scraped row data."""
    city, country_code = _parse_location(row_data.get("location", ""))
    
    return MiniclipJobListing(
        title=row_data.get("title", ""),
        location=row_data.get("location", ""),
        city=city,
        country_code=country_code,
        posted_date=row_data.get("posted_date", ""),
        job_url=row_data.get("job_url", "")
    )


def _filter_by_location(jobs: list[MiniclipJobListing], location: Optional[str]) -> list[MiniclipJobListing]:
    """Filter jobs by location."""
    if not location:
        return jobs
    
    location_lower = location.lower()
    
    # Handle country-level filtering
    if location_lower in COUNTRY_MAPPINGS:
        codes = COUNTRY_MAPPINGS[location_lower]
        return [j for j in jobs if j.country_code in codes]
    
    # Match by city or country code (partial match)
    return [
        j for j in jobs 
        if location_lower in j.city.lower() 
        or location_lower in j.country_code.lower()
        or location_lower in j.location.lower()
    ]


def _filter_by_query(jobs: list[MiniclipJobListing], query: Optional[str]) -> list[MiniclipJobListing]:
    """Filter jobs by search query."""
    if not query:
        return jobs
    
    query_lower = query.lower()
    return [j for j in jobs if query_lower in j.title.lower()]


async def scrape_miniclip_jobs(
    location: Optional[str] = "United Kingdom",
    query: Optional[str] = "",
    headless: bool = True,
    save_to_db: bool = False,
    db_connection_string: Optional[str] = None,
) -> list[MiniclipJobListing]:
    """Scrape job listings from Miniclip careers.
    
    Args:
        location: City or country to filter jobs by. Common values:
                  "London", "GB", "United Kingdom" - UK jobs
                  "Zoetermeer", "NL", "Netherlands" - Netherlands jobs
                  "Lisbon", "PT", "Portugal" - Portugal jobs
                  Set to None or empty string for all locations.
        query: Search term to filter jobs (matches title).
               Set to empty string for all jobs.
        headless: Whether to run browser in headless mode (default True).
        save_to_db: Whether to save results to a database (default False).
        db_connection_string: Database connection string. If not provided,
                              uses DATABASE_URL environment variable.
    
    Returns:
        List of MiniclipJobListing objects matching the search criteria.
    
    Example:
        # Get UK developer jobs
        jobs = await scrape_miniclip_jobs(location="United Kingdom", query="developer")
        
        # Get all jobs in Netherlands
        jobs = await scrape_miniclip_jobs(location="Netherlands")
        
        # Get all jobs worldwide
        jobs = await scrape_miniclip_jobs(location=None)
    """
    logger.info(f"Starting Miniclip job scrape - location: {location}, query: {query}")
    
    jobs: list[MiniclipJobListing] = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            logger.debug(f"Fetching jobs from {SEARCH_URL}")
            
            await page.goto(SEARCH_URL, timeout=60000, wait_until="load")
            await asyncio.sleep(3)
            
            # Get all job rows from the table
            rows = await page.query_selector_all("tr.data-row")
            logger.info(f"Found {len(rows)} job rows")
            
            for row in rows:
                try:
                    # Get cells
                    cells = await row.query_selector_all("td")
                    if len(cells) < 3:
                        continue
                    
                    title = (await cells[0].inner_text()).strip()
                    location_text = (await cells[1].inner_text()).strip()
                    posted_date = (await cells[2].inner_text()).strip()
                    
                    # Get job URL
                    link = await row.query_selector("a")
                    href = await link.get_attribute("href") if link else ""
                    job_url = f"{BASE_URL}{href}" if href and not href.startswith("http") else href
                    
                    row_data = {
                        "title": title,
                        "location": location_text,
                        "posted_date": posted_date,
                        "job_url": job_url
                    }
                    
                    job = _parse_job(row_data)
                    jobs.append(job)
                    
                except Exception as e:
                    logger.warning(f"Failed to parse job row: {e}")
            
            logger.info(f"Parsed {len(jobs)} jobs from page")
            
            # Apply filters client-side
            if location:
                jobs = _filter_by_location(jobs, location)
                logger.info(f"Jobs after location filter '{location}': {len(jobs)}")
            
            if query:
                jobs = _filter_by_query(jobs, query)
                logger.info(f"Jobs after query filter '{query}': {len(jobs)}")
            
            logger.info(f"Scraped {len(jobs)} jobs from Miniclip")
            
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


async def _save_to_database(jobs: list[MiniclipJobListing], connection_string: str) -> None:
    """Save job listings to database.
    
    Args:
        jobs: List of MiniclipJobListing objects to save.
        connection_string: Database connection string.
    """
    logger.info(f"Saving {len(jobs)} jobs to database")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(connection_string)
        
        # Create table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS miniclip_jobs (
                job_url VARCHAR(500) PRIMARY KEY,
                title VARCHAR(500),
                location VARCHAR(200),
                city VARCHAR(100),
                country_code VARCHAR(10),
                posted_date VARCHAR(50),
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert jobs
        for job in jobs:
            await conn.execute("""
                INSERT INTO miniclip_jobs 
                (job_url, title, location, city, country_code, posted_date)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (job_url) DO UPDATE SET
                    title = EXCLUDED.title,
                    location = EXCLUDED.location,
                    posted_date = EXCLUDED.posted_date,
                    scraped_at = CURRENT_TIMESTAMP
            """, job.job_url, job.title, job.location, job.city, 
                job.country_code, job.posted_date)
        
        await conn.close()
        logger.info(f"Successfully saved {len(jobs)} jobs to database")
        
    except ImportError:
        logger.error("asyncpg not installed. Run: pip install asyncpg")
    except Exception as e:
        logger.error(f"Failed to save to database: {e}")


async def scrape_miniclip_job_details(job_url: str, headless: bool = True) -> MiniclipJobDetails:
    """Scrape full details from a Miniclip job detail page.
    
    Args:
        job_url: URL to the Miniclip job detail page (e.g., https://careers.miniclip.com/job/Derby-Office-Assistant/1332014555/)
        headless: Run browser in headless mode
    
    Returns:
        MiniclipJobDetails with all job information
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        
        logger.info(f"Fetching job details from: {job_url}")
        await page.goto(job_url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        
        result = {}
        
        # Get body text
        body_text = await page.inner_text("body")
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
        
        # Title - usually in h1 or early in the page
        title_el = await page.query_selector("h1")
        result["title"] = (await title_el.inner_text()).strip() if title_el else ""
        
        # Location - look for location info
        result["location"] = ""
        for i, line in enumerate(lines):
            if any(x in line for x in ["London", "Derby", "Zoetermeer", "Lisbon", "Nottingham", "Izmir"]):
                if len(line) < 100:  # Avoid picking up text blocks
                    result["location"] = line.strip()
                    break
        
        # Department
        result["department"] = ""
        
        # Extract job_id from URL
        import re
        job_id_match = re.search(r'/(\d+)/?$', job_url)
        result["job_id"] = job_id_match.group(1) if job_id_match else ""
        
        # Build job_description from body text
        full_text = "\n".join(lines)
        
        # Find sections: Job Description, What will you be doing, What are we looking for
        desc_idx = full_text.find("Job Description")
        doing_idx = full_text.find("What will you be doing")
        looking_idx = full_text.find("What are we looking for")
        
        parts = []
        
        # Job Description section
        if desc_idx >= 0:
            end_idx = doing_idx if doing_idx > desc_idx else (looking_idx if looking_idx > desc_idx else len(full_text))
            parts.append(full_text[desc_idx:end_idx].strip())
        
        # What will you be doing section
        if doing_idx >= 0:
            end_idx = looking_idx if looking_idx > doing_idx else len(full_text)
            parts.append(f"\n\n{full_text[doing_idx:end_idx].strip()}")
        
        # What are we looking for section
        if looking_idx >= 0:
            parts.append(f"\n\n{full_text[looking_idx:len(full_text)].strip()}")
        
        result["job_description"] = "".join(parts) if parts else full_text[:3000]
        
        result["job_url"] = job_url
        result["apply_url"] = job_url  # Miniclip uses same page
        
        await browser.close()
        
        logger.info(f"Extracted details for: {result['title']}")
        return MiniclipJobDetails(**result)


async def main():
    """Test the scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape Miniclip job listings")
    parser.add_argument("--location", default="United Kingdom", help="Location to filter by")
    parser.add_argument("--query", default="", help="Search query")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run with visible browser")
    parser.add_argument("--save-to-db", action="store_true", help="Save results to database")
    parser.add_argument("--db-connection-string", help="Database connection string")
    parser.add_argument("--worldwide", action="store_true", help="Get all jobs worldwide")
    
    args = parser.parse_args()
    
    location = None if args.worldwide else args.location
    
    jobs = await scrape_miniclip_jobs(
        location=location,
        query=args.query,
        headless=args.headless,
        save_to_db=args.save_to_db,
        db_connection_string=args.db_connection_string,
    )
    
    print(f"\nFound {len(jobs)} jobs")
    print("=" * 60)
    
    for job in jobs[:10]:  # Show first 10
        print(f"\nTitle: {job.title}")
        print(f"Location: {job.location}")
        print(f"Posted: {job.posted_date}")
        print(f"URL: {job.job_url}")
        print("-" * 40)
    
    if len(jobs) > 10:
        print(f"\n... and {len(jobs) - 10} more jobs")


if __name__ == "__main__":
    asyncio.run(main())
