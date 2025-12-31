"""Rebellion Careers Scraper - Extract job listings from Rebellion's careers portal.

This module provides tools to scrape job listings from Rebellion's careers website
(careers.rebellion.com), which uses a Meilisearch API.

Primary Function:
    scrape_rebellion_jobs(location, query, headless, save_to_db, db_connection_string) -> list[RebellionJobListing]
    
    This is the main function an agent should use to retrieve Rebellion job listings.

Example Usage:
    ```python
    import asyncio
    from tools.scrapers.rebellion import scrape_rebellion_jobs
    
    # Get all jobs in United Kingdom (default)
    jobs = asyncio.run(scrape_rebellion_jobs())
    
    # Get jobs in a specific city
    jobs = asyncio.run(scrape_rebellion_jobs(location="Oxford"))
    jobs = asyncio.run(scrape_rebellion_jobs(location="Warwick"))
    
    # Search for specific roles
    jobs = asyncio.run(scrape_rebellion_jobs(query="programmer"))
    jobs = asyncio.run(scrape_rebellion_jobs(query="artist"))
    
    # Get all jobs (no location filter)
    jobs = asyncio.run(scrape_rebellion_jobs(location=None))
    
    # Save to database
    jobs = asyncio.run(scrape_rebellion_jobs(
        save_to_db=True,
        db_connection_string="postgresql://user:pass@localhost/db"
    ))
    
    # Access job data
    for job in jobs:
        print(f"Title: {job.title}")
        print(f"Location: {job.city}")
        print(f"Department: {job.department}")
        print(f"URL: {job.job_url}")
    ```

Return Data Structure:
    Returns a list of RebellionJobListing objects with:
    - title (str): Job title, e.g., "Senior Gameplay Programmer"
    - full_title (str): Full job title with code, e.g., "Senior Gameplay Programmer - COD54"
    - code (str): Job code, e.g., "COD54"
    - city (str): Job city, e.g., "Oxford", "Warwick"
    - country (str): Job country, e.g., "United Kingdom"
    - department (str): Department, e.g., "Project Team", "VFX Art"
    - department_hierarchy (list): Full department path
    - workplace_type (str): Work arrangement - "hybrid", "on_site", or "remote"
    - job_id (str): Rebellion job ID
    - shortcode (str): Job shortcode for applications
    - job_url (str): Direct URL to the job posting
    - application_url (str): Direct URL to apply

Supported Locations:
    - "Oxford" - Main Rebellion studio
    - "Warwick" - Warwick studio
    - "United Kingdom" - All UK locations (default)
    - None - All locations worldwide

Notes:
    - This function uses Playwright for API requests
    - The API uses Meilisearch with bearer token authentication
    - All jobs are returned in a single request (no pagination needed)
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
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
class RebellionJobListing:
    """A job listing from Rebellion search results.
    
    Attributes:
        title: The job title (e.g., "Senior Gameplay Programmer")
        full_title: Full job title with code (e.g., "Senior Gameplay Programmer - COD54")
        code: Job code (e.g., "COD54")
        city: Job city (e.g., "Oxford", "Warwick")
        country: Job country (e.g., "United Kingdom")
        department: Department (e.g., "Project Team", "VFX Art")
        department_hierarchy: Full department path
        workplace_type: Work arrangement - "hybrid", "on_site", or "remote"
        job_id: Rebellion job ID
        shortcode: Job shortcode for applications
        job_url: Direct URL to the job posting
        application_url: Direct URL to apply
    """
    title: str
    full_title: str
    code: str
    city: str
    country: str
    department: str
    department_hierarchy: list = field(default_factory=list)
    workplace_type: str = ""
    job_id: str = ""
    shortcode: str = ""
    job_url: str = ""
    application_url: str = ""


class RebellionScraper(BaseScraper):
    """Scraper for Rebellion careers pages."""
    
    URL_PATTERNS = ["careers.rebellion.com", "rebellion.workable.com"]
    
    async def scrape_job_listing(self, url: str, page: Page) -> ScrapedJob:
        """Extract job data from a Rebellion job detail page."""
        
        await page.wait_for_load_state("networkidle")
        
        title = await self.extract_text(page, "h1")
        location = await self.extract_text(page, "[data-ui='job-location']")
        description = await self.extract_text(page, "[data-ui='job-description']")
        
        return ScrapedJob(
            company="Rebellion",
            role=title,
            location=location,
            description=description,
            responsibilities=[],
            qualifications=[],
        )


# API configuration
API_URL = "https://searchapi.rebellion.com/indexes/rebellionJobs/search"
API_TOKEN = "fa384f27cc6304c80f27bcbf05541b83cc8cae5b209f9c8eda87519308996aa2"
BASE_URL = "https://careers.rebellion.com"


def _parse_job(job: dict) -> RebellionJobListing:
    """Parse a job posting from the Meilisearch API response."""
    location = job.get("location", {}) or {}
    dept_hierarchy = job.get("department_hierarchy", []) or []
    
    return RebellionJobListing(
        title=job.get("title", ""),
        full_title=job.get("full_title", ""),
        code=job.get("code", ""),
        city=location.get("city", ""),
        country=location.get("country", ""),
        department=job.get("department", ""),
        department_hierarchy=[d.get("name", "") for d in dept_hierarchy],
        workplace_type=job.get("workplace_type", ""),
        job_id=job.get("id", ""),
        shortcode=job.get("shortcode", ""),
        job_url=job.get("url", ""),
        application_url=job.get("application_url", "")
    )


def _filter_by_location(jobs: list[RebellionJobListing], location: Optional[str]) -> list[RebellionJobListing]:
    """Filter jobs by location."""
    if not location:
        return jobs
    
    location_lower = location.lower()
    
    # Handle country-level filtering
    if location_lower in ("united kingdom", "uk"):
        return [j for j in jobs if j.country.lower() == "united kingdom"]
    
    # Match by city (partial match)
    return [j for j in jobs if location_lower in j.city.lower() or location_lower in j.country.lower()]


async def scrape_rebellion_jobs(
    location: Optional[str] = "United Kingdom",
    query: Optional[str] = "",
    headless: bool = True,
    save_to_db: bool = False,
    db_connection_string: Optional[str] = None,
) -> list[RebellionJobListing]:
    """Scrape job listings from Rebellion careers.
    
    Args:
        location: City or country to filter jobs by. Common values:
                  "Oxford", "Warwick" - Specific cities
                  "United Kingdom" - All UK locations (default)
                  Set to None or empty string for all locations.
        query: Search term to filter jobs (e.g., "programmer", "artist").
               Uses Meilisearch full-text search.
               Set to empty string for all jobs.
        headless: Whether to run browser in headless mode (default True).
        save_to_db: Whether to save results to a database (default False).
        db_connection_string: Database connection string. If not provided,
                              uses DATABASE_URL environment variable.
    
    Returns:
        List of RebellionJobListing objects matching the search criteria.
    
    Example:
        # Get Oxford programming jobs
        jobs = await scrape_rebellion_jobs(location="Oxford", query="programmer")
        
        # Get all VFX jobs
        jobs = await scrape_rebellion_jobs(query="vfx")
        
        # Get all jobs worldwide
        jobs = await scrape_rebellion_jobs(location=None)
    """
    logger.info(f"Starting Rebellion job scrape - location: {location}, query: {query}")
    
    jobs: list[RebellionJobListing] = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Build search request
            search_body = {
                "q": query or "",
                "limit": 1000  # Get all jobs
            }
            
            logger.debug(f"Fetching jobs from Meilisearch API")
            
            response = await page.request.post(
                API_URL,
                data=json.dumps(search_body),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {API_TOKEN}"
                }
            )
            
            data = await response.json()
            
            if "hits" not in data:
                logger.error(f"API error: Invalid response - {data}")
                return jobs
            
            hits = data.get("hits", [])
            total = data.get("estimatedTotalHits", len(hits))
            logger.info(f"Total jobs from API: {total}")
            
            # Parse all jobs
            for job_data in hits:
                try:
                    job = _parse_job(job_data)
                    jobs.append(job)
                except Exception as e:
                    logger.warning(f"Failed to parse job: {e}")
            
            # Apply location filter client-side
            if location:
                jobs = _filter_by_location(jobs, location)
                logger.info(f"Jobs after location filter '{location}': {len(jobs)}")
            
            logger.info(f"Scraped {len(jobs)} jobs from Rebellion")
            
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


async def _save_to_database(jobs: list[RebellionJobListing], connection_string: str) -> None:
    """Save job listings to database.
    
    Args:
        jobs: List of RebellionJobListing objects to save.
        connection_string: Database connection string.
    """
    logger.info(f"Saving {len(jobs)} jobs to database")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(connection_string)
        
        # Create table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rebellion_jobs (
                job_id VARCHAR(50) PRIMARY KEY,
                shortcode VARCHAR(50),
                title VARCHAR(500),
                full_title VARCHAR(500),
                code VARCHAR(50),
                city VARCHAR(100),
                country VARCHAR(100),
                department VARCHAR(200),
                department_hierarchy TEXT[],
                workplace_type VARCHAR(50),
                job_url VARCHAR(500),
                application_url VARCHAR(500),
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert jobs
        for job in jobs:
            await conn.execute("""
                INSERT INTO rebellion_jobs 
                (job_id, shortcode, title, full_title, code, city, country, 
                 department, department_hierarchy, workplace_type, job_url, application_url)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (job_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    full_title = EXCLUDED.full_title,
                    city = EXCLUDED.city,
                    department = EXCLUDED.department,
                    workplace_type = EXCLUDED.workplace_type,
                    scraped_at = CURRENT_TIMESTAMP
            """, job.job_id, job.shortcode, job.title, job.full_title, job.code,
                job.city, job.country, job.department, job.department_hierarchy,
                job.workplace_type, job.job_url, job.application_url)
        
        await conn.close()
        logger.info(f"Successfully saved {len(jobs)} jobs to database")
        
    except ImportError:
        logger.error("asyncpg not installed. Run: pip install asyncpg")
    except Exception as e:
        logger.error(f"Failed to save to database: {e}")


async def main():
    """Test the scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape Rebellion job listings")
    parser.add_argument("--location", default="United Kingdom", help="Location to filter by")
    parser.add_argument("--query", default="", help="Search query")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run with visible browser")
    parser.add_argument("--save-to-db", action="store_true", help="Save results to database")
    parser.add_argument("--db-connection-string", help="Database connection string")
    parser.add_argument("--worldwide", action="store_true", help="Get all jobs worldwide")
    
    args = parser.parse_args()
    
    location = None if args.worldwide else args.location
    
    jobs = await scrape_rebellion_jobs(
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
        print(f"Location: {job.city}, {job.country}")
        print(f"Department: {job.department}")
        print(f"Workplace: {job.workplace_type}")
        print(f"URL: {job.job_url}")
        print("-" * 40)
    
    if len(jobs) > 10:
        print(f"\n... and {len(jobs) - 10} more jobs")


if __name__ == "__main__":
    asyncio.run(main())
