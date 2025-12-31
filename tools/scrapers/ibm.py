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
