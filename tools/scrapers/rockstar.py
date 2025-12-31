"""Rockstar Games Careers Scraper - Extract job listings from Rockstar's careers portal.

This module provides tools to scrape job listings from Rockstar Games' careers website
(rockstargames.com/careers), which uses a GraphQL API.

Primary Function:
    scrape_rockstar_jobs(location, query, headless, save_to_db, db_connection_string) -> list[RockstarJobListing]
    
    This is the main function an agent should use to retrieve Rockstar job listings.

Example Usage:
    ```python
    import asyncio
    from tools.scrapers.rockstar import scrape_rockstar_jobs
    
    # Get all jobs in United Kingdom (default - includes North, Leeds, Lincoln, London, Dundee)
    jobs = asyncio.run(scrape_rockstar_jobs())
    
    # Get jobs at a specific studio
    jobs = asyncio.run(scrape_rockstar_jobs(location="Rockstar North"))
    jobs = asyncio.run(scrape_rockstar_jobs(location="Rockstar New York"))
    jobs = asyncio.run(scrape_rockstar_jobs(location="Rockstar San Diego"))
    
    # Search for specific roles
    jobs = asyncio.run(scrape_rockstar_jobs(location="United Kingdom", query="programmer"))
    
    # Get all jobs worldwide (no location filter)
    jobs = asyncio.run(scrape_rockstar_jobs(location=None))
    
    # Filter by department
    jobs = asyncio.run(scrape_rockstar_jobs(query="code"))  # Code department
    jobs = asyncio.run(scrape_rockstar_jobs(query="art"))   # Art department
    
    # Save to database
    jobs = asyncio.run(scrape_rockstar_jobs(
        location="United Kingdom",
        save_to_db=True,
        db_connection_string="postgresql://user:pass@localhost/db"
    ))
    
    # Access job data
    for job in jobs:
        print(f"Title: {job.title}")
        print(f"Studio: {job.company}")
        print(f"Department: {job.department}")
        print(f"URL: {job.job_url}")
    ```

Return Data Structure:
    Returns a list of RockstarJobListing objects with:
    - title (str): Job title, e.g., "Senior Gameplay Programmer"
    - company (str): Rockstar studio, e.g., "Rockstar North", "Rockstar New York"
    - company_slug (str): URL slug for studio, e.g., "rockstar-north"
    - department (str): Department, e.g., "Code", "Art", "Animation"
    - department_slug (str): URL slug for department, e.g., "code"
    - job_id (str): Rockstar job ID (e.g., "6673341003")
    - job_url (str): Direct URL to the job posting

Supported Locations (studios):
    UK Studios: "Rockstar North", "Rockstar Leeds", "Rockstar Lincoln", 
                "Rockstar London", "Rockstar Dundee"
    US Studios: "Rockstar New York", "Rockstar San Diego", "Rockstar New England"
    Other: "Rockstar Toronto", "Rockstar India", "Rockstar Australia"
    
    Special values:
    - "United Kingdom" - All UK studios
    - "United States" - All US studios
    - None or "" - All studios worldwide

Notes:
    - This function uses Playwright for GraphQL API requests
    - The GraphQL API returns all jobs at once (no pagination needed)
    - Filtering by location/query is done client-side after fetching
"""

import asyncio
import json
import os
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
class RockstarJobListing:
    """A job listing from Rockstar Games search results.
    
    Attributes:
        title: The job title (e.g., "Senior Gameplay Programmer")
        company: Rockstar studio (e.g., "Rockstar North", "Rockstar New York")
        company_slug: URL slug for studio (e.g., "rockstar-north")
        department: Department (e.g., "Code", "Art", "Animation")
        department_slug: URL slug for department (e.g., "code")
        job_id: Rockstar job ID
        job_url: Direct URL to the job posting
    """
    title: str
    company: str
    company_slug: str
    department: str
    department_slug: str
    job_id: str
    job_url: str


@dataclass
class RockstarJobDetails:
    """Full details of a Rockstar Games job posting.
    
    Attributes:
        title: Job title
        company: Rockstar studio name
        department: Department name
        job_id: Rockstar job ID
        job_description: Full job description blob
        job_url: URL of the job detail page
        apply_url: URL to the application form
    """
    title: str
    company: str
    department: str
    job_id: str
    job_description: str
    job_url: str
    apply_url: str


class RockstarScraper(BaseScraper):
    """Scraper for Rockstar Games careers pages."""
    
    URL_PATTERNS = ["rockstargames.com/careers"]
    
    async def scrape_job_listing(self, url: str, page: Page) -> ScrapedJob:
        """Extract job data from a Rockstar job detail page."""
        
        await page.wait_for_load_state("networkidle")
        
        title = await self.extract_text(page, "h1")
        
        # Get company from office link
        company = ""
        office_link = await page.query_selector('a[href*="/careers/offices/"]')
        if office_link:
            company = await office_link.inner_text()
        
        description = await self.extract_text(page, "[class*='description']")
        
        return ScrapedJob(
            company=company or "Rockstar Games",
            role=title,
            location=company,
            description=description,
            responsibilities=[],
            qualifications=[],
        )


# GraphQL configuration
GRAPHQL_URL = "https://graph.rockstargames.com/"
GRAPHQL_HASH = "78cbb9ffc82e975403ecb541d89c2914114b6defeabd69337873d67c22baeb1a"
BASE_URL = "https://www.rockstargames.com/careers/openings"

# Studio groupings by region
UK_STUDIOS = ["Rockstar North", "Rockstar Leeds", "Rockstar Lincoln", "Rockstar London", "Rockstar Dundee"]
US_STUDIOS = ["Rockstar New York", "Rockstar San Diego", "Rockstar New England"]
ALL_STUDIOS = UK_STUDIOS + US_STUDIOS + ["Rockstar Toronto", "Rockstar India", "Rockstar Australia"]


def _parse_job(job: dict) -> RockstarJobListing:
    """Parse a job posting from the GraphQL API response."""
    company_data = job.get("company", {}) or {}
    
    return RockstarJobListing(
        title=job.get("title", ""),
        company=job.get("companyName", ""),
        company_slug=company_data.get("seo_url", ""),
        department=job.get("department", ""),
        department_slug=job.get("department_slug", ""),
        job_id=str(job.get("id", "")),
        job_url=f"https://www.rockstargames.com/careers/openings/position/{job.get('id', '')}"
    )


def _filter_by_location(jobs: list[RockstarJobListing], location: Optional[str]) -> list[RockstarJobListing]:
    """Filter jobs by location/studio."""
    if not location:
        return jobs
    
    location_lower = location.lower()
    
    # Handle region shortcuts
    if location_lower in ("united kingdom", "uk"):
        return [j for j in jobs if j.company in UK_STUDIOS]
    elif location_lower in ("united states", "usa", "us"):
        return [j for j in jobs if j.company in US_STUDIOS]
    
    # Match by studio name (partial match)
    return [j for j in jobs if location_lower in j.company.lower()]


def _filter_by_query(jobs: list[RockstarJobListing], query: Optional[str]) -> list[RockstarJobListing]:
    """Filter jobs by search query (matches title or department)."""
    if not query:
        return jobs
    
    query_lower = query.lower()
    return [
        j for j in jobs 
        if query_lower in j.title.lower() 
        or query_lower in j.department.lower()
        or query_lower in j.department_slug.lower()
    ]


async def scrape_rockstar_jobs(
    location: Optional[str] = "United Kingdom",
    query: Optional[str] = "",
    headless: bool = True,
    save_to_db: bool = False,
    db_connection_string: Optional[str] = None,
) -> list[RockstarJobListing]:
    """Scrape job listings from Rockstar Games careers.
    
    Args:
        location: Studio or region to filter jobs by. Common values:
                  "United Kingdom" - All UK studios
                  "United States" - All US studios
                  "Rockstar North", "Rockstar New York", etc. - Specific studio
                  Set to None or empty string for worldwide results.
        query: Search term to filter jobs (matches title or department).
               Set to empty string for all jobs.
        headless: Whether to run browser in headless mode (default True).
        save_to_db: Whether to save results to a database (default False).
        db_connection_string: Database connection string. If not provided,
                              uses DATABASE_URL environment variable.
    
    Returns:
        List of RockstarJobListing objects matching the search criteria.
    
    Example:
        # Get UK programming jobs
        jobs = await scrape_rockstar_jobs(location="United Kingdom", query="programmer")
        
        # Get all jobs at Rockstar North
        jobs = await scrape_rockstar_jobs(location="Rockstar North")
        
        # Get all jobs worldwide
        jobs = await scrape_rockstar_jobs(location=None)
    """
    logger.info(f"Starting Rockstar job scrape - location: {location}, query: {query}")
    
    jobs: list[RockstarJobListing] = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Build GraphQL request
            variables = json.dumps({"department": None, "query": None})
            extensions = json.dumps({
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": GRAPHQL_HASH
                }
            })
            
            url = (
                f"{GRAPHQL_URL}?origin=https://www.rockstargames.com"
                f"&operationName=OpeningsData"
                f"&variables={quote(variables)}"
                f"&extensions={quote(extensions)}"
            )
            
            logger.debug(f"Fetching jobs from GraphQL API")
            
            response = await page.request.get(url)
            data = await response.json()
            
            if not data or "data" not in data:
                logger.error(f"API error: Invalid response")
                return jobs
            
            positions = data.get("data", {}).get("jobsPositionList", [])
            logger.info(f"Total jobs from API: {len(positions)}")
            
            # Parse all jobs
            for job_data in positions:
                try:
                    job = _parse_job(job_data)
                    jobs.append(job)
                except Exception as e:
                    logger.warning(f"Failed to parse job: {e}")
            
            # Apply filters client-side
            if location:
                jobs = _filter_by_location(jobs, location)
                logger.info(f"Jobs after location filter '{location}': {len(jobs)}")
            
            if query:
                jobs = _filter_by_query(jobs, query)
                logger.info(f"Jobs after query filter '{query}': {len(jobs)}")
            
            logger.info(f"Scraped {len(jobs)} jobs from Rockstar Games")
            
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


async def _save_to_database(jobs: list[RockstarJobListing], connection_string: str) -> None:
    """Save job listings to database.
    
    Args:
        jobs: List of RockstarJobListing objects to save.
        connection_string: Database connection string.
    """
    logger.info(f"Saving {len(jobs)} jobs to database")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(connection_string)
        
        # Create table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rockstar_jobs (
                job_id VARCHAR(50) PRIMARY KEY,
                title VARCHAR(500),
                company VARCHAR(200),
                company_slug VARCHAR(100),
                department VARCHAR(200),
                department_slug VARCHAR(100),
                job_url VARCHAR(500),
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert jobs
        for job in jobs:
            await conn.execute("""
                INSERT INTO rockstar_jobs 
                (job_id, title, company, company_slug, department, department_slug, job_url)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (job_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    company = EXCLUDED.company,
                    department = EXCLUDED.department,
                    scraped_at = CURRENT_TIMESTAMP
            """, job.job_id, job.title, job.company, job.company_slug,
                job.department, job.department_slug, job.job_url)
        
        await conn.close()
        logger.info(f"Successfully saved {len(jobs)} jobs to database")
        
    except ImportError:
        logger.error("asyncpg not installed. Run: pip install asyncpg")
    except Exception as e:
        logger.error(f"Failed to save to database: {e}")


async def scrape_rockstar_job_details(job_url: str, headless: bool = True) -> RockstarJobDetails:
    """Scrape full details from a Rockstar Games job detail page.
    
    Args:
        job_url: URL to the Rockstar job detail page (e.g., https://www.rockstargames.com/careers/openings/position/6673341003)
        headless: Run browser in headless mode
    
    Returns:
        RockstarJobDetails with all job information
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
        
        # Title is usually in h1
        title_el = await page.query_selector("h1")
        result["title"] = (await title_el.inner_text()).strip() if title_el else ""
        
        # Company/studio - extract from page or URL
        result["company"] = ""
        for line in lines:
            if "Rockstar" in line and any(x in line for x in ["North", "New York", "San Diego", "Leeds", "Lincoln", "London", "Dundee", "Toronto", "India"]):
                result["company"] = line.strip()
                break
        
        # Department - look for department marker
        result["department"] = ""
        for i, line in enumerate(lines):
            if "Department" in line or line in ["Code", "Art", "Animation", "Design", "Audio", "QA", "Production", "Marketing"]:
                result["department"] = line
                break
        
        # Extract job_id from URL
        import re
        job_id_match = re.search(r'/position/(\d+)', job_url)
        result["job_id"] = job_id_match.group(1) if job_id_match else ""
        
        # Build job_description from body text
        full_text = "\n".join(lines)
        
        # Find sections: WHAT WE DO, RESPONSIBILITIES, REQUIREMENTS, PLUSES, HOW TO APPLY
        what_we_do_idx = full_text.upper().find("WHAT WE DO")
        resp_idx = full_text.upper().find("RESPONSIBILITIES")
        req_idx = full_text.upper().find("REQUIREMENTS")
        pluses_idx = full_text.upper().find("PLUSES")
        how_idx = full_text.upper().find("HOW TO APPLY")
        
        parts = []
        
        # What We Do section
        if what_we_do_idx >= 0:
            end_idx = resp_idx if resp_idx > what_we_do_idx else (req_idx if req_idx > what_we_do_idx else len(full_text))
            parts.append(full_text[what_we_do_idx:end_idx].strip())
        
        # Responsibilities section
        if resp_idx >= 0:
            end_idx = req_idx if req_idx > resp_idx else (pluses_idx if pluses_idx > resp_idx else len(full_text))
            parts.append(f"\n\n{full_text[resp_idx:end_idx].strip()}")
        
        # Requirements section
        if req_idx >= 0:
            end_idx = pluses_idx if pluses_idx > req_idx else (how_idx if how_idx > req_idx else len(full_text))
            parts.append(f"\n\n{full_text[req_idx:end_idx].strip()}")
        
        # Pluses section
        if pluses_idx >= 0:
            end_idx = how_idx if how_idx > pluses_idx else len(full_text)
            parts.append(f"\n\n{full_text[pluses_idx:end_idx].strip()}")
        
        result["job_description"] = "".join(parts) if parts else full_text[:3000]
        
        result["job_url"] = job_url
        result["apply_url"] = job_url  # Rockstar uses same page
        
        await browser.close()
        
        logger.info(f"Extracted details for: {result['title']}")
        return RockstarJobDetails(**result)


async def main():
    """Test the scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape Rockstar Games job listings")
    parser.add_argument("--location", default="United Kingdom", help="Location/studio to filter by")
    parser.add_argument("--query", default="", help="Search query (title or department)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Run with visible browser")
    parser.add_argument("--save-to-db", action="store_true", help="Save results to database")
    parser.add_argument("--db-connection-string", help="Database connection string")
    parser.add_argument("--worldwide", action="store_true", help="Get all jobs worldwide")
    
    args = parser.parse_args()
    
    location = None if args.worldwide else args.location
    
    jobs = await scrape_rockstar_jobs(
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
        print(f"Studio: {job.company}")
        print(f"Department: {job.department}")
        print(f"URL: {job.job_url}")
        print("-" * 40)
    
    if len(jobs) > 10:
        print(f"\n... and {len(jobs) - 10} more jobs")


if __name__ == "__main__":
    asyncio.run(main())
