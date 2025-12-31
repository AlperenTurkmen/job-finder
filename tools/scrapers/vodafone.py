"""Vodafone Careers Scraper - Extract job listings from Vodafone's careers portal.

This module provides tools to scrape job listings from Vodafone's careers website
(jobs.vodafone.com), which uses the PCSX search API.

Primary Function:
    scrape_vodafone_jobs(location, query, headless, save_to_db, db_connection_string) -> list[VodafoneJobListing]
    
    This is the main function an agent should use to retrieve Vodafone job listings.

Example Usage:
    ```python
    import asyncio
    from tools.scrapers.vodafone import scrape_vodafone_jobs
    
    # Get all jobs in United Kingdom (default)
    jobs = asyncio.run(scrape_vodafone_jobs())
    
    # Get jobs in a specific country
    jobs = asyncio.run(scrape_vodafone_jobs(location="United Kingdom"))
    jobs = asyncio.run(scrape_vodafone_jobs(location="Germany"))
    jobs = asyncio.run(scrape_vodafone_jobs(location="India"))
    
    # Search for specific roles
    jobs = asyncio.run(scrape_vodafone_jobs(location="United Kingdom", query="engineer"))
    
    # Get all jobs worldwide (no location filter)
    jobs = asyncio.run(scrape_vodafone_jobs(location=None))
    
    # Save to database
    jobs = asyncio.run(scrape_vodafone_jobs(
        location="United Kingdom",
        save_to_db=True,
        db_connection_string="postgresql://user:pass@localhost/db"
    ))
    
    # Access job data
    for job in jobs:
        print(f"Title: {job.title}")
        print(f"Location: {job.location}")
        print(f"Department: {job.department}")
        print(f"URL: {job.job_url}")
    ```

Return Data Structure:
    Returns a list of VodafoneJobListing objects with:
    - title (str): Job title, e.g., "Senior Software Engineer"
    - location (str): Primary job location, e.g., "London, United Kingdom"
    - locations (list[str]): All job locations (for multi-location roles)
    - department (str): Department, e.g., "Technology", "Commercial"
    - work_location_option (str): Work arrangement - "onsite", "remote_local", or "hybrid"
    - job_id (str): Vodafone job ID (e.g., "563018688187359")
    - display_job_id (str): Display job ID (e.g., "268845")
    - job_url (str): Direct URL to the job posting

Supported Locations (countries):
    - "United Kingdom", "Germany", "India", "Romania"
    - "Türkiye", "Hungary", "Egypt", "Greece"
    - "Spain", "Portugal", "Albania", "Czech Republic"
    - Or any country listed on Vodafone careers

Notes:
    - This function uses Playwright for API requests
    - The API limits results to 10 per request, pagination is handled automatically
    - Network requests may take 5-15 seconds depending on result count
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field
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
    # Fallback if base.py doesn't exist or for standalone execution
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
class VodafoneJobListing:
    """A job listing from Vodafone search results.
    
    Attributes:
        title: The job title (e.g., "Senior Software Engineer")
        location: Primary job location (e.g., "London, United Kingdom")
        locations: All job locations (for multi-location roles)
        department: Department (e.g., "Technology", "Commercial")
        work_location_option: Work arrangement - "onsite", "remote_local", or "hybrid"
        job_id: Vodafone internal job ID
        display_job_id: Display-friendly job ID
        job_url: Direct URL to the job posting on Vodafone careers
    """
    title: str
    location: str
    locations: list = field(default_factory=list)
    department: str = ""
    work_location_option: str = ""
    job_id: str = ""
    display_job_id: str = ""
    job_url: str = ""


class VodafoneScraper(BaseScraper):
    """Scraper for Vodafone careers pages."""
    
    URL_PATTERNS = ["jobs.vodafone.com"]
    
    async def scrape_job_listing(self, url: str, page: Page) -> ScrapedJob:
        """Extract job data from a Vodafone job detail page."""
        
        # Wait for content to load
        try:
            await page.wait_for_selector("h1", timeout=10000)
        except Exception:
            pass
        
        title = await self.extract_text(page, "h1")
        location = await self.extract_text(page, "[data-testid='location']")
        description = await self.extract_text(page, "[data-testid='job-description']")
        
        return ScrapedJob(
            company="Vodafone",
            role=title,
            location=location,
            description=description,
            responsibilities=[],
            qualifications=[],
        )


BASE_URL = "https://jobs.vodafone.com/careers"
API_URL = "https://jobs.vodafone.com/api/pcsx/search"
PAGE_SIZE = 10  # API limit


def _parse_job(job: dict) -> VodafoneJobListing:
    """Parse a job posting from the Vodafone API response."""
    locations = job.get("locations", [])
    primary_location = job.get("location", "") or (locations[0] if locations else "")
    
    return VodafoneJobListing(
        title=job.get("name", ""),
        location=primary_location,
        locations=locations,
        department=job.get("department", ""),
        work_location_option=job.get("workLocationOption", ""),
        job_id=str(job.get("id", "")),
        display_job_id=str(job.get("displayJobId", "")),
        job_url=f"https://jobs.vodafone.com{job.get('positionUrl', '')}"
    )


async def scrape_vodafone_jobs(
    location: Optional[str] = "United Kingdom",
    query: Optional[str] = "",
    headless: bool = True,
    save_to_db: bool = False,
    db_connection_string: Optional[str] = None,
) -> list[VodafoneJobListing]:
    """Scrape job listings from Vodafone careers.
    
    Args:
        location: Country/city to filter jobs by. Common values:
                  "United Kingdom", "Germany", "India", "Romania", etc.
                  Set to None or empty string for worldwide results.
        query: Search term to filter jobs (e.g., "engineer", "data scientist").
               Set to empty string for all jobs.
        headless: Whether to run browser in headless mode (default True).
        save_to_db: Whether to save results to a database (default False).
        db_connection_string: Database connection string. If not provided,
                              uses DATABASE_URL environment variable.
    
    Returns:
        List of VodafoneJobListing objects matching the search criteria.
    
    Example:
        # Get UK engineering jobs
        jobs = await scrape_vodafone_jobs(location="United Kingdom", query="engineer")
        
        # Get all jobs in Germany
        jobs = await scrape_vodafone_jobs(location="Germany")
        
        # Get all jobs worldwide
        jobs = await scrape_vodafone_jobs(location=None)
    """
    logger.info(f"Starting Vodafone job scrape - location: {location}, query: {query}")
    
    jobs: list[VodafoneJobListing] = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Build query parameters
            location_param = quote(location) if location else ""
            query_param = quote(query) if query else ""
            
            # First request to get total count
            url = f"{API_URL}?domain=vodafone.com&query={query_param}&location={location_param}&start=0&num={PAGE_SIZE}"
            logger.debug(f"Fetching initial page: {url}")
            
            response = await page.request.get(url)
            data = await response.json()
            
            # Status is 200 (integer) for success
            if data.get("status") != 200:
                logger.error(f"API error: {data.get('error', 'Unknown error')}")
                return jobs
            
            total_count = data.get("data", {}).get("count", 0)
            logger.info(f"Total jobs found: {total_count}")
            
            # Parse first page results
            positions = data.get("data", {}).get("positions", [])
            for job_data in positions:
                try:
                    job = _parse_job(job_data)
                    jobs.append(job)
                except Exception as e:
                    logger.warning(f"Failed to parse job: {e}")
            
            # Paginate through remaining results
            start = PAGE_SIZE
            while start < total_count:
                url = f"{API_URL}?domain=vodafone.com&query={query_param}&location={location_param}&start={start}&num={PAGE_SIZE}"
                logger.debug(f"Fetching page at offset {start}")
                
                response = await page.request.get(url)
                data = await response.json()
                
                # Status is 200 (integer) for success
                if data.get("status") != 200:
                    logger.warning(f"API error at offset {start}: {data.get('error', 'Unknown error')}")
                    break
                
                positions = data.get("data", {}).get("positions", [])
                if not positions:
                    logger.debug(f"No more positions at offset {start}")
                    break
                
                for job_data in positions:
                    try:
                        job = _parse_job(job_data)
                        jobs.append(job)
                    except Exception as e:
                        logger.warning(f"Failed to parse job: {e}")
                
                start += PAGE_SIZE
            
            logger.info(f"Scraped {len(jobs)} jobs from Vodafone")
            
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


async def _save_to_database(jobs: list[VodafoneJobListing], connection_string: str) -> None:
    """Save job listings to database.
    
    Args:
        jobs: List of VodafoneJobListing objects to save.
        connection_string: Database connection string.
    """
    logger.info(f"Saving {len(jobs)} jobs to database")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(connection_string)
        
        # Create table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vodafone_jobs (
                job_id VARCHAR(50) PRIMARY KEY,
                display_job_id VARCHAR(50),
                title VARCHAR(500),
                location VARCHAR(500),
                locations TEXT[],
                department VARCHAR(200),
                work_location_option VARCHAR(50),
                job_url VARCHAR(500),
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert jobs
        for job in jobs:
            await conn.execute("""
                INSERT INTO vodafone_jobs 
                (job_id, display_job_id, title, location, locations, department, work_location_option, job_url)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (job_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    location = EXCLUDED.location,
                    locations = EXCLUDED.locations,
                    department = EXCLUDED.department,
                    work_location_option = EXCLUDED.work_location_option,
                    scraped_at = CURRENT_TIMESTAMP
            """, job.job_id, job.display_job_id, job.title, job.location, 
                job.locations, job.department, job.work_location_option, job.job_url)
        
        await conn.close()
        logger.info(f"Successfully saved {len(jobs)} jobs to database")
        
    except ImportError:
        logger.error("asyncpg not installed. Run: pip install asyncpg")
    except Exception as e:
        logger.error(f"Failed to save to database: {e}")


async def main():
    """Test the scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape Vodafone job listings")
    parser.add_argument("--location", default="United Kingdom", help="Location to filter by")
    parser.add_argument("--query", default="", help="Search query")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run with visible browser")
    parser.add_argument("--save-to-db", action="store_true", help="Save results to database")
    parser.add_argument("--db-connection-string", help="Database connection string")
    parser.add_argument("--worldwide", action="store_true", help="Get all jobs worldwide")
    
    args = parser.parse_args()
    
    location = None if args.worldwide else args.location
    
    jobs = await scrape_vodafone_jobs(
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
        print(f"Department: {job.department}")
        print(f"Work Type: {job.work_location_option}")
        print(f"URL: {job.job_url}")
        print("-" * 40)
    
    if len(jobs) > 10:
        print(f"\n... and {len(jobs) - 10} more jobs")


if __name__ == "__main__":
    asyncio.run(main())
