"""Unified Job Scraper Orchestrator.

Runs all scrapers, filters by keywords, and saves to database.
- Jobs matching keywords: saves full details (including job_description)
- Jobs not matching keywords: saves basic listing info only

Usage:
    python tools/scrapers/run_all_scrapers.py
    python tools/scrapers/run_all_scrapers.py --companies netflix,meta,google
    python tools/scrapers/run_all_scrapers.py --no-details  # Skip scraping job details
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Callable, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from utils.logging import get_logger
from utils.db_client import JobFinderDB

logger = get_logger(__name__)

# Import all scrapers
from tools.scrapers.netflix import scrape_netflix_jobs, scrape_netflix_job_details, NetflixJobListing, NetflixJobDetails
from tools.scrapers.samsung import scrape_samsung_jobs, scrape_samsung_job_details, SamsungJobListing, SamsungJobDetails
from tools.scrapers.meta import scrape_meta_jobs, scrape_meta_job_details, MetaJobListing, MetaJobDetails
from tools.scrapers.vodafone import scrape_vodafone_jobs, scrape_vodafone_job_details, VodafoneJobListing, VodafoneJobDetails
from tools.scrapers.rockstar import scrape_rockstar_jobs, scrape_rockstar_job_details, RockstarJobListing, RockstarJobDetails
from tools.scrapers.rebellion import scrape_rebellion_jobs, scrape_rebellion_job_details, RebellionJobListing, RebellionJobDetails
from tools.scrapers.miniclip import scrape_miniclip_jobs, scrape_miniclip_job_details, MiniclipJobListing, MiniclipJobDetails
from tools.scrapers.google import scrape_google_jobs, scrape_google_job_details, GoogleJobListing, GoogleJobDetails
from tools.scrapers.ibm import scrape_ibm_jobs, scrape_ibm_job_details, IBMJobListing, IBMJobDetails


@dataclass
class ScraperConfig:
    """Configuration for a company scraper."""
    name: str
    domain: str
    careers_url: str
    list_scraper: Callable
    details_scraper: Callable
    get_title: Callable
    get_url: Callable
    get_location: Callable
    get_department: Callable = lambda x: ""
    get_work_type: Callable = lambda x: ""
    get_job_id: Callable = lambda x: ""
    location_map: Optional[dict] = None  # Map generic locations to scraper-specific formats


# Location mapping for scrapers that need different formats
# Meta uses "London, UK" format instead of "United Kingdom"
META_LOCATION_MAP = {
    "United Kingdom": "London, UK",
    "United States": "Menlo Park, CA",
    "Germany": "Berlin, Germany",
    "Ireland": "Dublin, Ireland",
    "France": "Paris, France",
}


# Scraper configurations for each company
SCRAPERS = {
    "netflix": ScraperConfig(
        name="Netflix",
        domain="netflix.com",
        careers_url="https://jobs.netflix.com",
        list_scraper=scrape_netflix_jobs,
        details_scraper=scrape_netflix_job_details,
        get_title=lambda j: j.title,
        get_url=lambda j: j.job_url,
        get_location=lambda j: j.location,
        get_department=lambda j: getattr(j, 'teams', ''),
        get_work_type=lambda j: getattr(j, 'work_type', ''),
        get_job_id=lambda j: getattr(j, 'job_id', ''),
    ),
    "samsung": ScraperConfig(
        name="Samsung",
        domain="samsung.com",
        careers_url="https://sec.wd3.myworkdayjobs.com/Samsung_Careers",
        list_scraper=scrape_samsung_jobs,
        details_scraper=scrape_samsung_job_details,
        get_title=lambda j: j.title,
        get_url=lambda j: j.job_url,
        get_location=lambda j: j.location,
        get_work_type=lambda j: getattr(j, 'remote_type', ''),
        get_job_id=lambda j: getattr(j, 'job_id', ''),
    ),
    "meta": ScraperConfig(
        name="Meta",
        domain="meta.com",
        careers_url="https://www.metacareers.com/jobs",
        list_scraper=scrape_meta_jobs,
        details_scraper=scrape_meta_job_details,
        get_title=lambda j: j.title,
        get_url=lambda j: j.job_url,
        get_location=lambda j: j.location,
        get_department=lambda j: ', '.join(getattr(j, 'teams', []) or []),  # Meta returns list, convert to string
        get_job_id=lambda j: getattr(j, 'job_id', ''),
        location_map=META_LOCATION_MAP,  # Meta needs "London, UK" format
    ),
    "vodafone": ScraperConfig(
        name="Vodafone",
        domain="vodafone.com",
        careers_url="https://jobs.vodafone.com",
        list_scraper=scrape_vodafone_jobs,
        details_scraper=scrape_vodafone_job_details,
        get_title=lambda j: j.title,
        get_url=lambda j: j.job_url,
        get_location=lambda j: j.location,
        get_department=lambda j: getattr(j, 'department', ''),
        get_work_type=lambda j: getattr(j, 'work_location_option', ''),
        get_job_id=lambda j: getattr(j, 'job_id', ''),
    ),
    "rockstar": ScraperConfig(
        name="Rockstar Games",
        domain="rockstargames.com",
        careers_url="https://www.rockstargames.com/careers",
        list_scraper=scrape_rockstar_jobs,
        details_scraper=scrape_rockstar_job_details,
        get_title=lambda j: j.title,
        get_url=lambda j: j.job_url,
        get_location=lambda j: getattr(j, 'company', ''),  # Rockstar uses company as location (studio)
        get_department=lambda j: getattr(j, 'department', ''),
        get_job_id=lambda j: getattr(j, 'job_id', ''),
    ),
    "rebellion": ScraperConfig(
        name="Rebellion",
        domain="rebellion.com",
        careers_url="https://rebellion.workable.com",
        list_scraper=scrape_rebellion_jobs,
        details_scraper=scrape_rebellion_job_details,
        get_title=lambda j: j.title,
        get_url=lambda j: j.job_url,
        get_location=lambda j: f"{getattr(j, 'city', '')}, {getattr(j, 'country', '')}",
        get_department=lambda j: getattr(j, 'department', ''),
        get_work_type=lambda j: getattr(j, 'workplace_type', ''),
        get_job_id=lambda j: getattr(j, 'job_id', ''),
    ),
    "miniclip": ScraperConfig(
        name="Miniclip",
        domain="miniclip.com",
        careers_url="https://careers.miniclip.com",
        list_scraper=scrape_miniclip_jobs,
        details_scraper=scrape_miniclip_job_details,
        get_title=lambda j: j.title,
        get_url=lambda j: j.job_url,
        get_location=lambda j: j.location,
        get_job_id=lambda j: "",  # Miniclip doesn't have job_id in listing
    ),
    "google": ScraperConfig(
        name="Google",
        domain="google.com",
        careers_url="https://www.google.com/about/careers",
        list_scraper=scrape_google_jobs,
        details_scraper=scrape_google_job_details,
        get_title=lambda j: j.title,
        get_url=lambda j: j.job_url,
        get_location=lambda j: j.location,
        get_job_id=lambda j: getattr(j, 'job_id', ''),
    ),
    "ibm": ScraperConfig(
        name="IBM",
        domain="ibm.com",
        careers_url="https://ibmglobal.avature.net/en_UK/careers",
        list_scraper=scrape_ibm_jobs,
        details_scraper=scrape_ibm_job_details,
        get_title=lambda j: j.title,
        get_url=lambda j: j.job_url,
        get_location=lambda j: j.location,
        get_department=lambda j: getattr(j, 'team', ''),
        get_job_id=lambda j: getattr(j, 'job_id', ''),
    ),
}


def load_keywords() -> List[str]:
    """Load keywords from config file."""
    config_path = Path(__file__).parent.parent.parent / "config" / "scraper_keywords.json"
    with open(config_path) as f:
        config = json.load(f)
    return config.get("job_title_keywords", [])


import re

def matches_keywords(title: str, keywords: List[str]) -> bool:
    """Check if job title contains any of the keywords as whole words (case-insensitive).
    
    Uses word boundary regex to prevent false positives like 'AI' matching 'AdvAIser'.
    """
    title_lower = title.lower()
    for kw in keywords:
        # Use word boundary regex: \b matches word boundaries
        pattern = r'\b' + re.escape(kw.lower()) + r'\b'
        if re.search(pattern, title_lower):
            return True
    return False


async def scrape_company(
    config: ScraperConfig,
    db: JobFinderDB,
    keywords: List[str],
    scrape_details: bool = True,
    headless: bool = True,
    location: str = "United Kingdom",
) -> dict:
    """Scrape all jobs from a company and save to database.
    
    Args:
        config: Scraper configuration for the company
        db: Database client
        keywords: List of keywords to filter by
        scrape_details: Whether to scrape full details for matching jobs
        headless: Run browser in headless mode
        location: Location filter for scraping
        
    Returns:
        Dict with stats: {total, matched, saved, details_scraped}
    """
    stats = {"total": 0, "matched": 0, "saved": 0, "details_scraped": 0, "errors": 0}
    
    logger.info(f"🔍 Scraping {config.name}...")
    
    # Get or create company
    company_id = await db.upsert_company(
        name=config.name,
        domain=config.domain,
        careers_url=config.careers_url,
    )
    
    # Apply location mapping if scraper needs different format
    scraper_location = location
    if config.location_map and location in config.location_map:
        scraper_location = config.location_map[location]
        logger.info(f"  📍 Using location '{scraper_location}' for {config.name} (mapped from '{location}')")
    
    # Scrape job listings
    try:
        jobs = await config.list_scraper(location=scraper_location, headless=headless)
        stats["total"] = len(jobs)
        logger.info(f"📋 Found {len(jobs)} jobs at {config.name}")
    except Exception as e:
        logger.error(f"❌ Failed to scrape {config.name} listings: {e}")
        stats["errors"] += 1
        return stats
    
    # Process each job - ONLY save jobs that match keywords
    for job in jobs:
        title = config.get_title(job)
        job_url = config.get_url(job)
        
        # Skip jobs that don't match keywords
        if not matches_keywords(title, keywords):
            continue
            
        stats["matched"] += 1
        
        # Prepare basic job data
        job_data = {
            "company_id": company_id,
            "title": title,
            "job_url": job_url,
            "location": config.get_location(job),
            "department": config.get_department(job),
            "work_type": config.get_work_type(job),
            "job_id": config.get_job_id(job),
            "description": None,  # Will be filled if we scrape details
        }
        
        # Scrape full job details if enabled
        if scrape_details:
            try:
                logger.info(f"  📖 Scraping details for: {title[:50]}...")
                details = await config.details_scraper(job_url, headless=headless)
                
                # Extract description from details
                if hasattr(details, 'job_description'):
                    job_data["description"] = details.job_description
                    stats["details_scraped"] += 1
                    logger.info(f"  ✅ Got {len(details.job_description)} chars of description")
            except Exception as e:
                logger.warning(f"  ⚠️ Failed to scrape details for {title[:40]}: {e}")
        
        # Save to database
        try:
            await db.upsert_job(**job_data)
            stats["saved"] += 1
        except Exception as e:
            logger.error(f"  ❌ Failed to save job {title[:40]}: {e}")
            stats["errors"] += 1
    
    logger.info(f"✅ {config.name}: {stats['total']} total, {stats['matched']} matched, {stats['details_scraped']} with details")
    return stats


async def run_all_scrapers(
    companies: Optional[List[str]] = None,
    scrape_details: bool = True,
    headless: bool = True,
    location: str = "United Kingdom",
    db_connection_string: Optional[str] = None,
) -> dict:
    """Run all scrapers and save results to database.
    
    Args:
        companies: List of company keys to scrape (None = all)
        scrape_details: Whether to scrape full details for matching jobs
        headless: Run browser in headless mode
        location: Location filter for scraping
        db_connection_string: Database connection string
        
    Returns:
        Dict with total stats across all companies
    """
    # Load keywords
    keywords = load_keywords()
    logger.info(f"📝 Loaded {len(keywords)} keywords: {', '.join(keywords[:5])}...")
    
    # Get database connection
    db_url = db_connection_string or os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("No database connection string provided. Set DATABASE_URL env var or pass --db-connection-string")
    
    # Initialize database
    db = JobFinderDB(db_url)
    await db.connect()
    
    # Determine which scrapers to run
    if companies:
        scrapers_to_run = {k: v for k, v in SCRAPERS.items() if k in companies}
    else:
        scrapers_to_run = SCRAPERS
    
    # Aggregate stats
    total_stats = {
        "companies": 0,
        "total_jobs": 0,
        "matched_jobs": 0,
        "saved_jobs": 0,
        "details_scraped": 0,
        "errors": 0,
    }
    
    try:
        for key, config in scrapers_to_run.items():
            try:
                stats = await scrape_company(
                    config=config,
                    db=db,
                    keywords=keywords,
                    scrape_details=scrape_details,
                    headless=headless,
                    location=location,
                )
                total_stats["companies"] += 1
                total_stats["total_jobs"] += stats["total"]
                total_stats["matched_jobs"] += stats["matched"]
                total_stats["saved_jobs"] += stats["saved"]
                total_stats["details_scraped"] += stats["details_scraped"]
                total_stats["errors"] += stats["errors"]
            except Exception as e:
                logger.error(f"❌ Failed to process {config.name}: {e}")
                total_stats["errors"] += 1
    finally:
        await db.close()
    
    return total_stats


def main():
    parser = argparse.ArgumentParser(description="Run all job scrapers with keyword filtering")
    parser.add_argument(
        "--companies",
        type=str,
        default=None,
        help="Comma-separated list of companies to scrape (default: all). "
             f"Options: {', '.join(SCRAPERS.keys())}"
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Skip scraping full job details (only save listing info)"
    )
    parser.add_argument(
        "--location",
        type=str,
        default="United Kingdom",
        help="Location filter for job search (default: United Kingdom)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)"
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Run browser with visible window"
    )
    parser.add_argument(
        "--db-connection-string",
        type=str,
        default=None,
        help="Database connection string (default: from DATABASE_URL env var)"
    )
    
    args = parser.parse_args()
    
    # Parse companies
    companies = None
    if args.companies:
        companies = [c.strip().lower() for c in args.companies.split(",")]
        invalid = [c for c in companies if c not in SCRAPERS]
        if invalid:
            print(f"Error: Unknown companies: {', '.join(invalid)}")
            print(f"Valid options: {', '.join(SCRAPERS.keys())}")
            sys.exit(1)
    
    # Run scrapers
    stats = asyncio.run(run_all_scrapers(
        companies=companies,
        scrape_details=not args.no_details,
        headless=args.headless,
        location=args.location,
        db_connection_string=args.db_connection_string,
    ))
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 SCRAPING SUMMARY")
    print("=" * 60)
    print(f"Companies scraped:    {stats['companies']}")
    print(f"Total jobs found:     {stats['total_jobs']}")
    print(f"Jobs matching filter: {stats['matched_jobs']}")
    print(f"Jobs with details:    {stats['details_scraped']}")
    print(f"Jobs saved to DB:     {stats['saved_jobs']} (only matched jobs)")
    print(f"Errors:               {stats['errors']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
