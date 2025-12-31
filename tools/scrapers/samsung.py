"""Samsung Careers Scraper - Extract job listings from Samsung's careers portal.

This module provides tools to scrape job listings from Samsung's careers website
(sec.wd3.myworkdayjobs.com), which is powered by Workday ATS.

Primary Function:
    scrape_samsung_jobs(location, query) -> list[SamsungJobListing]
    
    This is the main function an agent should use to retrieve Samsung job listings.

Example Usage:
    ```python
    import asyncio
    from tools.scrapers.samsung import scrape_samsung_jobs
    
    # Get all jobs in United Kingdom (default)
    jobs = asyncio.run(scrape_samsung_jobs())
    
    # Get jobs in a specific country
    jobs = asyncio.run(scrape_samsung_jobs(location="United Kingdom"))
    jobs = asyncio.run(scrape_samsung_jobs(location="Germany"))
    jobs = asyncio.run(scrape_samsung_jobs(location="United States of America"))
    
    # Search for specific roles
    jobs = asyncio.run(scrape_samsung_jobs(location="United Kingdom", query="engineer"))
    
    # Get all jobs worldwide (no location filter)
    jobs = asyncio.run(scrape_samsung_jobs(location=None))
    
    # Access job data
    for job in jobs:
        print(f"Title: {job.title}")
        print(f"Location: {job.location}")
        print(f"URL: {job.job_url}")
    ```

Return Data Structure:
    Returns a list of SamsungJobListing objects with:
    - title (str): Job title, e.g., "Senior Software Engineer"
    - location (str): Job location, e.g., "Samsung House, Chertsey, United Kingdom"
    - remote_type (str): Work arrangement - "On-site", "Remote", or "Hybrid"
    - posted_on (str): When the job was posted, e.g., "Posted Today", "Posted 30+ Days Ago"
    - job_id (str): Samsung job reference number (e.g., "R112424")
    - job_url (str): Direct URL to the job posting

Supported Locations (countries):
    - "United Kingdom", "Germany", "United States of America"
    - "France", "Netherlands", "Poland", "Italy", "Spain"
    - "India", "Singapore", "Canada", "Brazil"
    - Or any country listed on Samsung careers

Notes:
    - This function uses Playwright for browser automation (headless by default)
    - The scraper uses Workday's JSON API for reliable data extraction
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
class SamsungJobListing:
    """A job listing from Samsung search results.
    
    Attributes:
        title: The job title (e.g., "Senior Software Engineer")
        location: Job location (e.g., "Samsung House, Chertsey, United Kingdom")
        remote_type: Work arrangement - "On-site", "Remote", or "Hybrid"
        posted_on: When posted (e.g., "Posted Today", "Posted 30+ Days Ago")
        job_id: Samsung job reference number (e.g., "R112424")
        job_url: Direct URL to the job posting on Samsung careers
    """
    title: str
    location: str
    remote_type: str
    posted_on: str
    job_id: str
    job_url: str


@dataclass
class SamsungJobDetails:
    """Full details of a Samsung job posting from the job detail page.
    
    Attributes:
        title: Job title
        location: Job location
        remote_type: Work arrangement (Hybrid, On-site, Remote)
        time_type: Employment type (Full time, Part time)
        posted_on: When the job was posted
        job_id: Samsung job reference number
        job_description: Full job description blob (description + responsibilities + qualifications + benefits)
        job_url: URL of the job detail page
        apply_url: URL to the application form
    """
    title: str
    location: str
    remote_type: str
    time_type: str
    posted_on: str
    job_id: str
    job_description: str
    job_url: str
    apply_url: str


class SamsungScraper(BaseScraper):
    """Scraper for Samsung careers pages (Workday ATS)."""
    
    URL_PATTERNS = ["sec.wd3.myworkdayjobs.com"]
    
    async def scrape_job_listing(self, url: str, page: Page) -> ScrapedJob:
        """Extract job data from a Samsung job detail page."""
        
        # Wait for content to load
        try:
            await page.wait_for_selector("[data-automation-id='jobPostingHeader']", timeout=10000)
        except Exception:
            pass
        
        title = await self.extract_text(page, "[data-automation-id='jobPostingHeader']")
        location = await self.extract_text(page, "[data-automation-id='locations']")
        description = await self.extract_text(page, "[data-automation-id='jobPostingDescription']")
        
        return ScrapedJob(
            company="Samsung",
            role=title,
            location=location,
            description=description,
            responsibilities=[],
            qualifications=[],
        )


BASE_URL = "https://sec.wd3.myworkdayjobs.com/Samsung_Careers"
API_URL = "https://sec.wd3.myworkdayjobs.com/wday/cxs/sec/Samsung_Careers/jobs"

def _parse_job(job: dict) -> SamsungJobListing:
    """Parse a job posting from the Workday API response."""
    # Extract job ID from bulletFields or externalPath
    job_id = ""
    if job.get("bulletFields"):
        job_id = job["bulletFields"][0]
    elif job.get("externalPath"):
        # Extract from path like /job/.../Title_R112424
        path = job["externalPath"]
        if "_R" in path:
            job_id = "R" + path.split("_R")[-1]
    
    external_path = job.get("externalPath", "")
    job_url = f"{BASE_URL}{external_path}" if external_path else ""
    
    return SamsungJobListing(
        title=job.get("title", "").strip(),
        location=job.get("locationsText", ""),
        remote_type=job.get("remoteType", ""),
        posted_on=job.get("postedOn", ""),
        job_id=job_id,
        job_url=job_url,
    )


# Country ID mapping for location filters
COUNTRY_IDS = {
    "United States of America": "bc33aa3152ec42d4995f4791a106ed09",
    "United States": "bc33aa3152ec42d4995f4791a106ed09",
    "USA": "bc33aa3152ec42d4995f4791a106ed09",
    "Türkiye": "c2e3bac5bbbb47b29dfc6e8b56a1586e",
    "Turkey": "c2e3bac5bbbb47b29dfc6e8b56a1586e",
    "Germany": "dcc5b7608d8644b3a93716604e78e995",
    "United Kingdom": "29247e57dbaf46fb855b224e03170bc7",
    "UK": "29247e57dbaf46fb855b224e03170bc7",
    "Indonesia": "b31234dbcdda4da9ba8fa073c5944e36",
    "Italy": "8cd04a563fd94da7b06857a79faaf815",
    "Poland": "131d5ac7e3ee4d7b962bdc96e498e412",
    "India": "c4f78be1a8f14da0ab49ce1162348a5e",
    "Singapore": "80938777cac5440fab50d729f9634969",
    "Canada": "a30a87ed25634629aa6c3958aa2b91ea",
    "Ukraine": "a4051ef996ac40778d4c79e3f2dedfd2",
    "Philippines": "e56f1daf83e04bacae794ba5c5593560",
    "France": "54c5b6971ffb4bf0b116fe7651ec789a",
    "Netherlands": "9696868b09c64d52a62ee13b052383cc",
    "Thailand": "873d0f604e3b458c990cb4d83a5c0f14",
    "Brazil": "1a29bb1357b240ab99a2fa755cc87c0e",
    "Switzerland": "187134fccb084a0ea9b4b95f23890dbe",
    "Romania": "f2e609fe92974a55a05fc1cdc2852122",
    "Croatia": "1face6f426c14de9979a134697da0db3",
    "Austria": "d004c0d1a6c84511ab048669fcdf9fd7",
    "Belgium": "a04ea128f43a42e59b1e6a19e8f0b374",
    "Hungary": "9db257f5937e4421b2fac64eec6832f8",
    "Slovenia": "db69d9f0446c11de98360015c5e6daf6",
    "Chile": "53fe09ef12b9408682a1d2439823f2e0",
    "Israel": "084562884af243748dad7c84c304d89a",
    "Malaysia": "972dc4ba8d454bc0b893ff84b1529077",
    "Latvia": "1c026f3b1b8640d8bdfcb95466663e4d",
    "Czechia": "fc078443155c4ad294201ecf5a61a499",
    "Colombia": "e8106cd6a3534f2dba6fdee2d41db89d",
    "Spain": "bd34c524a6a04ae6915f5d96fa086199",
    "Greece": "566388c1eb974c42bd9e3da4c2f57d60",
    "Morocco": "7aaca3f6fc774f16802a4df4718a5b53",
    "Vietnam": "db69e8c8446c11de98360015c5e6daf6",
    "Bulgaria": "25f4875dc598484dbeee857eb2d81652",
    "Panama": "a390372e575c41ecb7240c51ce9067bd",
    "Estonia": "038b0482bfea403abb61c9bcc3d7eb60",
    "Ireland": "04a05835925f45b3a59406a2a6b72c8a",
    "Sweden": "6a800a4736884df5826858d435650f45",
    "Myanmar": "8ae7375b330441989443b02b66699ff9",
    "Tunisia": "db69e508446c11de98360015c5e6daf6",
    "Moldova": "db69d266446c11de98360015c5e6daf6",
    "Laos": "db69cbe0446c11de98360015c5e6daf6",
    "Cambodia": "db69bf9c446c11de98360015c5e6daf6",
}


async def scrape_samsung_jobs(
    location: str | None = "United Kingdom",
    query: str | None = None,
    headless: bool = True,
    save_to_db: bool = False,
    db_connection_string: str | None = None,
) -> list[SamsungJobListing]:
    """Scrape job listings from Samsung careers website.
    
    This is the primary function for retrieving Samsung job listings.
    It launches a headless browser, makes API requests to Workday,
    and extracts all matching job postings.
    
    Args:
        location: Country to filter jobs. Examples:
            - "United Kingdom" (default)
            - "Germany", "United States of America", "France"
            - "Netherlands", "Poland", "India", "Singapore"
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
        List of SamsungJobListing objects, each containing:
            - title (str): Job title
            - location (str): Job location  
            - remote_type (str): Work arrangement
            - posted_on (str): When posted
            - job_id (str): Samsung job ID
            - job_url (str): URL to apply/view details
        
        Returns empty list if no jobs found.
    
    Examples:
        >>> jobs = await scrape_samsung_jobs()  # UK jobs
        >>> jobs = await scrape_samsung_jobs(location="Germany")
        >>> jobs = await scrape_samsung_jobs(location=None)  # worldwide
        >>> jobs = await scrape_samsung_jobs(query="engineer")
        >>> jobs = await scrape_samsung_jobs(location="United Kingdom", query="engineer")
        
        >>> # Save to database automatically
        >>> jobs = await scrape_samsung_jobs(
        ...     location="United Kingdom",
        ...     save_to_db=True,
        ...     db_connection_string=os.getenv("DATABASE_URL")
        ... )
        
        >>> for job in jobs:
        ...     print(job.title)
    
    Note:
        - Requires Playwright and Chromium browser installed
        - Takes 5-15 seconds depending on number of results
        - Uses Workday JSON API for reliable data extraction
    """
    from utils.logging import get_logger
    logger = get_logger(__name__)
    
    logger.info(f"🌐 Scraping Samsung careers (location={location}, query={query})")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            # Build facets for filtering
            applied_facets = {}
            if location:
                country_id = COUNTRY_IDS.get(location)
                if country_id:
                    applied_facets["Location_Country"] = [country_id]
                    logger.info(f"📍 Filtering by country: {location}")
                else:
                    logger.warning(f"⚠️  Unknown location '{location}', fetching all jobs")
            
            # Fetch all jobs with pagination
            jobs: list[SamsungJobListing] = []
            offset = 0
            limit = 20
            total = None
            
            logger.info("📡 Fetching jobs from Workday API...")
            
            # First request to get total count
            first_response = await page.request.post(API_URL, data={
                "appliedFacets": applied_facets,
                "limit": limit,
                "offset": 0,
                "searchText": query or ""
            })
            
            first_data = await first_response.json()
            total = first_data.get("total", 0)
            logger.info(f"📊 Total jobs available: {total}")
            
            # Process first batch
            job_postings = first_data.get("jobPostings", [])
            for job in job_postings:
                jobs.append(_parse_job(job))
            
            logger.info(f"📥 Fetched {len(jobs)}/{total} jobs (offset=0)")
            offset = limit
            
            # Continue pagination if needed
            while len(jobs) < total:
                response = await page.request.post(API_URL, data={
                    "appliedFacets": applied_facets,
                    "limit": limit,
                    "offset": offset,
                    "searchText": query or ""
                })
                
                data = await response.json()
                job_postings = data.get("jobPostings", [])
                
                if not job_postings:
                    break
                
                for job in job_postings:
                    jobs.append(_parse_job(job))
                
                logger.info(f"📥 Fetched {len(jobs)}/{total} jobs (offset={offset})")
                offset += limit
            
            logger.info(f"✅ Extracted {len(jobs)} jobs")
            
            # Save to database if requested
            if save_to_db:
                if not db_connection_string:
                    raise ValueError("db_connection_string required when save_to_db=True")
                
                logger.info("💾 Saving to database...")
                # Import here to avoid circular dependency
                from utils.db_client import save_jobs_to_db
                
                # Convert SamsungJobListing objects to dicts
                job_dicts = [
                    {
                        "title": job.title,
                        "job_url": job.job_url,
                        "location": job.location,
                        "department": "",
                        "business_unit": "",
                        "work_type": job.remote_type,
                        "job_id": job.job_id,
                    }
                    for job in jobs
                ]
                
                result = await save_jobs_to_db(
                    company_name="Samsung",
                    company_domain="samsung.com",
                    careers_url=BASE_URL,
                    jobs=job_dicts,
                    db_connection_string=db_connection_string
                )
                
                logger.info(f"✅ Database: {result['inserted']} inserted, {result['updated']} updated")
            
            return jobs
            
        finally:
            await browser.close()


async def get_samsung_locations(headless: bool = True) -> list[dict]:
    """Get all available country filters from Samsung careers.
    
    Returns:
        List of location dictionaries with keys:
            - id (str): Location identifier for API filtering
            - descriptor (str): Display name (e.g., "United Kingdom")
            - count (int): Number of jobs in that location
    """
    from utils.logging import get_logger
    logger = get_logger(__name__)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Fetch initial data to get facets
            response = await page.request.post(API_URL, data={
                "appliedFacets": {},
                "limit": 1,
                "offset": 0,
                "searchText": ""
            })
            
            data = await response.json()
            facets = data.get("facets", [])
            
            # Find location facet
            for facet in facets:
                if facet.get("facetParameter") == "Location_Country":
                    return facet.get("values", [])
            
            return []
            
        finally:
            await browser.close()


async def get_samsung_remote_types(headless: bool = True) -> list[dict]:
    """Get all available remote type filters from Samsung careers.
    
    Returns:
        List of remote type dictionaries with keys:
            - id (str): Remote type identifier for API filtering
            - descriptor (str): Display name (e.g., "On-site", "Remote", "Hybrid")
            - count (int): Number of jobs of that type
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            response = await page.request.post(API_URL, data={
                "appliedFacets": {},
                "limit": 1,
                "offset": 0,
                "searchText": ""
            })
            
            data = await response.json()
            facets = data.get("facets", [])
            
            for facet in facets:
                if facet.get("facetParameter") == "remoteType":
                    return facet.get("values", [])
            
            return []
            
        finally:
            await browser.close()


async def scrape_samsung_job_details(job_url: str, headless: bool = True) -> SamsungJobDetails:
    """Scrape full details from a Samsung job detail page.
    
    Args:
        job_url: URL to the Samsung job detail page
        headless: Run browser in headless mode
    
    Returns:
        SamsungJobDetails with all job information
    """
    from utils.logging import get_logger
    logger = get_logger(__name__)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        
        logger.info(f"Fetching job details from: {job_url}")
        await page.goto(job_url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        
        result = {}
        
        # Title (h2)
        title_el = await page.query_selector("h2")
        result["title"] = (await title_el.inner_text()).strip() if title_el else ""
        
        # Get body text for parsing
        body_text = await page.inner_text("body")
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
        
        # Parse metadata by finding labels
        result["remote_type"] = ""
        result["location"] = ""
        result["time_type"] = ""
        result["posted_on"] = ""
        result["job_id"] = ""
        
        for i, line in enumerate(lines):
            if line == "remote type" and i + 1 < len(lines):
                result["remote_type"] = lines[i + 1]
            elif line == "locations" and i + 1 < len(lines):
                result["location"] = lines[i + 1]
            elif line == "time type" and i + 1 < len(lines):
                result["time_type"] = lines[i + 1]
            elif line == "posted on" and i + 1 < len(lines):
                result["posted_on"] = lines[i + 1]
            elif line == "job requisition id" and i + 1 < len(lines):
                result["job_id"] = lines[i + 1]
        
        # Find Position Summary, Role and Responsibilities, Skills sections
        full_text = "\n".join(lines)
        
        pos_idx = full_text.find("Position Summary")
        role_idx = full_text.find("Role and Responsibilities")
        skills_idx = full_text.find("Skills and Qualifications")
        benefits_idx = full_text.find("Employee Benefits")
        
        # Extract individual sections
        description = ""
        if pos_idx >= 0 and role_idx > pos_idx:
            description = full_text[pos_idx + len("Position Summary"):role_idx].strip()
        
        responsibilities = []
        if role_idx >= 0 and skills_idx > role_idx:
            resp_text = full_text[role_idx + len("Role and Responsibilities"):skills_idx].strip()
            responsibilities = [r.strip() for r in resp_text.split("\n") if r.strip()]
        
        qualifications = []
        if skills_idx >= 0:
            end_idx = benefits_idx if benefits_idx > skills_idx else len(full_text)
            skills_text = full_text[skills_idx + len("Skills and Qualifications"):end_idx].strip()
            qualifications = [q.strip() for q in skills_text.split("\n") if q.strip()]
        
        benefits = []
        if benefits_idx >= 0:
            loc_idx = full_text.find("Location and Hybrid Working")
            end_idx = loc_idx if loc_idx > benefits_idx else len(full_text) - 500
            benefits_text = full_text[benefits_idx + len("Employee Benefits"):end_idx].strip()
            benefits = [b.strip() for b in benefits_text.split("\n") if b.strip()]
        
        # Combine into single job_description blob
        parts = []
        if description:
            parts.append(f"Position Summary:\n{description}")
        if responsibilities:
            parts.append("\n\nRole and Responsibilities:\n" + "\n".join(f"• {r}" for r in responsibilities))
        if qualifications:
            parts.append("\n\nSkills and Qualifications:\n" + "\n".join(f"• {q}" for q in qualifications))
        if benefits:
            parts.append("\n\nEmployee Benefits:\n" + "\n".join(f"• {b}" for b in benefits))
        result["job_description"] = "".join(parts)
        
        result["job_url"] = job_url
        
        # Get apply URL
        apply_btn = await page.query_selector("a:has-text(\"Apply\")")
        if apply_btn:
            result["apply_url"] = await apply_btn.get_attribute("href") or ""
        else:
            result["apply_url"] = ""
        
        await browser.close()
        
        logger.info(f"Extracted details for: {result['title']}")
        return SamsungJobDetails(**result)


async def main():
    """Example usage of the Samsung scraper with database integration."""
    import os
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use environment variables directly
    
    # Example 1: Just scrape jobs (no database)
    print("=== Scraping Samsung jobs (no database) ===")
    jobs = await scrape_samsung_jobs(location="United Kingdom")
    
    if jobs:
        print(f"\nFound {len(jobs)} Samsung job(s):\n")
        for i, job in enumerate(jobs[:5], 1):  # Show first 5
            print(f"{i}. {job.title}")
            print(f"   Location: {job.location}")
            print(f"   Remote Type: {job.remote_type}")
            print(f"   Posted: {job.posted_on}")
            print(f"   Job ID: {job.job_id}")
            print(f"   URL: {job.job_url}\n")
    else:
        print("No jobs found.")
    
    # Example 2: Scrape and save to database
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        print("\n=== Scraping and saving to database ===")
        jobs = await scrape_samsung_jobs(
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
