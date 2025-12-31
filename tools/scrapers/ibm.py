"""
IBM Careers Scraper

Scrapes job listings from IBM Careers (ibm.com/uk-en/careers/search).

Usage:
    python tools/scrapers/ibm.py --location "United Kingdom"
    python tools/scrapers/ibm.py --location "United States" --query "engineer"
    python tools/scrapers/ibm.py --worldwide --max-pages 5
"""

import asyncio
import argparse
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from playwright.async_api import async_playwright

from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class IBMJobListing:
    """Represents a job listing from IBM Careers."""
    title: str
    team: str
    level: str
    location: str
    job_id: str
    job_url: str
    company: str = "IBM"


@dataclass(slots=True)
class IBMJobDetails:
    """Full details of an IBM job posting.
    
    Attributes:
        title: Job title
        location: Job location
        team: Team/department name
        job_id: IBM job ID
        job_description: Full job description blob
        job_url: URL of the job detail page
        apply_url: URL to the application form
    """
    title: str
    location: str
    team: str
    job_id: str
    job_description: str
    job_url: str
    apply_url: str


async def scrape_ibm_jobs(
    location: str | None = "United Kingdom",
    query: str | None = None,
    headless: bool = True,
    save_to_db: bool = False,
    db_connection_string: str | None = None,
    max_pages: int = 10,
) -> list[IBMJobListing]:
    """
    Scrape job listings from IBM Careers.
    
    Args:
        location: Country to filter by (e.g., "United Kingdom", "United States"). None for worldwide.
        query: Optional search query to filter jobs.
        headless: Run browser in headless mode.
        save_to_db: Whether to save results to database.
        db_connection_string: Database connection string if saving to DB.
        max_pages: Maximum number of pages to scrape (30 jobs per page).
    
    Returns:
        List of IBMJobListing objects.
    """
    logger.info(f"Starting IBM job scrape - location: {location}, query: {query}")
    
    jobs: list[IBMJobListing] = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        
        current_page = 1
        
        while current_page <= max_pages:
            # Build URL with parameters
            params = {}
            if query:
                params["q"] = query
            if location:
                params["field_keyword_05[0]"] = location
            if current_page > 1:
                params["p"] = str(current_page)
            
            url = "https://www.ibm.com/uk-en/careers/search"
            if params:
                url += "?" + urlencode(params)
            
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            
            # Get total job count on first page
            if current_page == 1:
                body_text = await page.inner_text("body")
                total_match = re.search(r"of ([\d,]+) items", body_text)
                if total_match:
                    total_jobs = int(total_match.group(1).replace(",", ""))
                    logger.info(f"Total jobs available: {total_jobs}")
            
            # Get job cards
            job_links = await page.query_selector_all('a[href*="JobDetail"]')
            
            if not job_links:
                logger.info(f"No more jobs found on page {current_page}")
                break
            
            page_jobs = 0
            for link in job_links:
                try:
                    href = await link.get_attribute("href")
                    text = await link.inner_text()
                    
                    # Parse the job card text
                    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
                    
                    if len(lines) >= 4:
                        team = lines[0]
                        title = lines[1]
                        level = lines[2]
                        job_location = lines[3]
                    elif len(lines) >= 2:
                        team = ""
                        title = lines[0]
                        level = lines[1] if len(lines) > 1 else ""
                        job_location = lines[2] if len(lines) > 2 else ""
                    else:
                        continue
                    
                    # Extract job ID from URL
                    job_id_match = re.search(r"jobId=(\d+)", href)
                    job_id = job_id_match.group(1) if job_id_match else ""
                    
                    job = IBMJobListing(
                        title=title,
                        team=team,
                        level=level,
                        location=job_location,
                        job_id=job_id,
                        job_url=href,
                    )
                    jobs.append(job)
                    page_jobs += 1
                    
                except Exception as e:
                    logger.warning(f"Error parsing job card: {e}")
                    continue
            
            logger.info(f"Page {current_page}: {page_jobs} jobs")
            
            # Check if we've reached the last page (less than 30 jobs)
            if page_jobs < 30:
                break
            
            current_page += 1
        
        await browser.close()
    
    logger.info(f"Scraped {len(jobs)} jobs from IBM")
    
    if save_to_db and db_connection_string:
        logger.info("Database saving not yet implemented")
    
    return jobs


async def scrape_ibm_job_details(
    job_url: str, 
    headless: bool = True,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> IBMJobDetails:
    """Scrape full details from an IBM job detail page.
    
    Args:
        job_url: URL to the IBM job detail page (e.g., https://ibmglobal.avature.net/en_UK/careers/JobDetail?jobId=81102)
        headless: Run browser in headless mode
        max_retries: Maximum number of retry attempts for rate-limited requests
        retry_delay: Base delay between retries (increases exponentially)
    
    Returns:
        IBMJobDetails with all job information
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        
        logger.info(f"Fetching job details from: {job_url}")
        
        # Retry logic for rate limiting (406 errors)
        body_text = ""
        for attempt in range(max_retries):
            await page.goto(job_url, wait_until="load", timeout=60000)
            await page.wait_for_timeout(3000)
            
            body_text = await page.inner_text("body")
            
            # Check for rate limiting (406 Not Acceptable)
            if "406 Not Acceptable" in body_text or "not acceptable" in body_text.lower():
                if attempt < max_retries - 1:
                    delay = retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Rate limited (406), retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                    await page.wait_for_timeout(delay * 1000)
                    continue
                else:
                    logger.error(f"Rate limited after {max_retries} attempts: {job_url}")
                    break
            else:
                # Success - break out of retry loop
                break
        
        result = {}
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
        
        # Title - find after "< Back to search results" marker, usually line 6
        result["title"] = ""
        for i, line in enumerate(lines):
            if line == "< Back to search results" and i + 1 < len(lines):
                result["title"] = lines[i + 1]
                break
        if not result["title"]:
            # Fallback: try h1
            title_el = await page.query_selector("h1")
            result["title"] = (await title_el.inner_text()).strip() if title_el else lines[5] if len(lines) > 5 else ""
        
        # Location - usually right after title
        result["location"] = ""
        for i, line in enumerate(lines):
            if line == result["title"] and i + 1 < len(lines):
                result["location"] = lines[i + 1]
                break
        
        # Team - usually after location (e.g., "Consulting")
        result["team"] = ""
        for i, line in enumerate(lines):
            if line == result["location"] and i + 1 < len(lines):
                result["team"] = lines[i + 1]
                break
        
        # Extract job_id from URL
        job_id_match = re.search(r'jobId=(\d+)', job_url)
        result["job_id"] = job_id_match.group(1) if job_id_match else ""
        
        # Build job_description from body text
        full_text = "\n".join(lines)
        
        # IBM Avature uses sections: Introduction, Your role and responsibilities, Required technical and professional expertise
        intro_idx = full_text.find("Introduction")
        role_idx = full_text.find("Your role and responsibilities")
        req_idx = full_text.find("Required technical and professional expertise")
        pref_idx = full_text.find("Preferred technical and professional expertise")
        
        parts = []
        
        # Introduction section
        if intro_idx >= 0:
            end_idx = role_idx if role_idx > intro_idx else (req_idx if req_idx > intro_idx else len(full_text))
            parts.append(full_text[intro_idx:end_idx].strip())
        
        # Role and responsibilities section
        if role_idx >= 0:
            end_idx = req_idx if req_idx > role_idx else (pref_idx if pref_idx > role_idx else len(full_text))
            parts.append(f"\n\n{full_text[role_idx:end_idx].strip()}")
        
        # Required expertise section
        if req_idx >= 0:
            end_idx = pref_idx if pref_idx > req_idx else len(full_text)
            parts.append(f"\n\n{full_text[req_idx:end_idx].strip()}")
        
        # Preferred expertise section
        if pref_idx >= 0:
            parts.append(f"\n\n{full_text[pref_idx:len(full_text)].strip()}")
        
        result["job_description"] = "".join(parts) if parts else full_text[:3000]
        
        result["job_url"] = job_url
        result["apply_url"] = job_url  # IBM Avature uses same page
        
        await browser.close()
        
        logger.info(f"Extracted details for: {result['title']}")
        return IBMJobDetails(**result)


def main():
    parser = argparse.ArgumentParser(description="Scrape IBM job listings")
    parser.add_argument("--location", type=str, default="United Kingdom",
                        help="Country to filter by (e.g., 'United Kingdom', 'United States')")
    parser.add_argument("--query", type=str, default=None,
                        help="Search query to filter jobs")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="Run browser in headless mode")
    parser.add_argument("--no-headless", action="store_false", dest="headless",
                        help="Run browser with visible window")
    parser.add_argument("--max-pages", type=int, default=10,
                        help="Maximum number of pages to scrape")
    parser.add_argument("--worldwide", action="store_true",
                        help="Search all locations (no location filter)")
    parser.add_argument("--save-to-db", action="store_true",
                        help="Save results to database")
    parser.add_argument("--db-connection-string", type=str,
                        help="Database connection string")
    
    args = parser.parse_args()
    
    location = None if args.worldwide else args.location
    
    jobs = asyncio.run(scrape_ibm_jobs(
        location=location,
        query=args.query,
        headless=args.headless,
        save_to_db=args.save_to_db,
        db_connection_string=args.db_connection_string,
        max_pages=args.max_pages,
    ))
    
    print(f"\nFound {len(jobs)} jobs")
    print("=" * 70)
    
    for job in jobs[:10]:
        print(f"\nTitle: {job.title}")
        print(f"Team: {job.team}")
        print(f"Level: {job.level}")
        print(f"Location: {job.location}")
        print(f"URL: {job.job_url}")
        print("-" * 50)
    
    if len(jobs) > 10:
        print(f"\n... and {len(jobs) - 10} more jobs")


if __name__ == "__main__":
    main()
