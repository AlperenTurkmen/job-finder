#!/usr/bin/env python3
"""
Scrape Jobs Without Database

Scrapes jobs and saves them to JSON files (no database required).
Perfect for testing or when PostgreSQL is not available.

Usage:
    python scripts/scrape_to_json.py netflix --limit 5
    python scripts/scrape_to_json.py netflix meta google --limit 10
"""

import asyncio
import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright
from utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

# Available scrapers
SCRAPERS = {
    "netflix": {
        "name": "Netflix",
        "search_url": "https://explore.jobs.netflix.net/careers/search?query=%2A&sort_by=relevance&domain=netflix.com&location=United%20Kingdom",
        "job_card_selector": "[data-ui='job-card']"
    },
    "meta": {
        "name": "Meta",
        "search_url": "https://www.metacareers.com/jobs",
        "job_card_selector": "a[href*='/jobs/']"
    },
    # Add more as needed
}


async def scrape_simple(company_id: str, max_jobs: int = 100):
    """Simple scraper that extracts basic job info without database.
    
    Args:
        company_id: Company to scrape
        max_jobs: Maximum jobs to fetch
        
    Returns:
        List of job dictionaries
    """
    if company_id not in SCRAPERS:
        logger.error(f"Scraper not configured for: {company_id}")
        return []
    
    config = SCRAPERS[company_id]
    logger.info(f"Scraping {config['name']}...")
    
    jobs = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            logger.info(f"Loading {config['search_url']}")
            await page.goto(config['search_url'], wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            # Get all job cards
            job_cards = await page.query_selector_all(config['job_card_selector'])
            logger.info(f"Found {len(job_cards)} job cards")
            
            for idx, card in enumerate(job_cards[:max_jobs], 1):
                try:
                    # Extract basic info from card
                    title = await card.inner_text()
                    href = await card.get_attribute("href")
                    
                    # Build full URL if relative
                    if href and not href.startswith("http"):
                        from urllib.parse import urljoin
                        href = urljoin(config['search_url'], href)
                    
                    job = {
                        "company": config['name'],
                        "title": title.strip() if title else "Unknown",
                        "job_url": href,
                        "scraped_at": datetime.utcnow().isoformat()
                    }
                    
                    jobs.append(job)
                    logger.info(f"  [{idx}/{min(len(job_cards), max_jobs)}] {job['title'][:60]}")
                    
                except Exception as e:
                    logger.warning(f"Failed to extract job {idx}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Scraping failed: {e}", exc_info=True)
        
        finally:
            await browser.close()
    
    return jobs


async def scrape_and_save(company_ids: list, max_jobs_per_company: int = 100):
    """Scrape jobs and save to JSON files.
    
    Args:
        company_ids: List of company IDs
        max_jobs_per_company: Max jobs per company
    """
    logger.info("=" * 60)
    logger.info("Scraping Jobs to JSON (No Database Required)")
    logger.info(f"Companies: {', '.join(company_ids)}")
    logger.info(f"Max jobs per company: {max_jobs_per_company}")
    logger.info("=" * 60)
    
    all_jobs = {}
    
    for company_id in company_ids:
        jobs = await scrape_simple(company_id, max_jobs_per_company)
        all_jobs[company_id] = jobs
        logger.info(f"✓ {company_id}: {len(jobs)} jobs scraped\n")
    
    # Save to JSON files
    output_dir = PROJECT_ROOT / "data" / "scraped_jobs"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for company_id, jobs in all_jobs.items():
        if not jobs:
            continue
            
        filename = f"{company_id}_{timestamp}.json"
        filepath = output_dir / filename
        
        with open(filepath, "w") as f:
            json.dump({
                "company": company_id,
                "scraped_at": datetime.utcnow().isoformat(),
                "job_count": len(jobs),
                "jobs": jobs
            }, f, indent=2)
        
        logger.info(f"💾 Saved {len(jobs)} jobs to: {filepath}")
    
    # Create combined file
    combined_file = output_dir / f"all_jobs_{timestamp}.json"
    with open(combined_file, "w") as f:
        json.dump({
            "scraped_at": datetime.utcnow().isoformat(),
            "companies": list(all_jobs.keys()),
            "total_jobs": sum(len(jobs) for jobs in all_jobs.values()),
            "jobs_by_company": all_jobs
        }, f, indent=2)
    
    logger.info(f"\n💾 All jobs saved to: {combined_file}")
    
    # Summary
    total = sum(len(jobs) for jobs in all_jobs.values())
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ Complete! Scraped {total} total jobs")
    logger.info(f"📁 Output directory: {output_dir}")
    logger.info("=" * 60)
    
    logger.info("\n📋 Next Steps:")
    logger.info("  1. Start PostgreSQL: brew services start postgresql@14")
    logger.info("  2. Import to database: python tools/import_roles.py")
    logger.info("  3. Or continue with: python scripts/quick_scrape.py (with DB running)")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape jobs to JSON (no database required)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/scrape_to_json.py netflix --limit 5
  python scripts/scrape_to_json.py netflix meta --limit 10
  
This script works WITHOUT PostgreSQL!
        """
    )
    
    parser.add_argument(
        "companies",
        nargs="+",
        choices=list(SCRAPERS.keys()),
        help="Company IDs to scrape"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum jobs per company (default: 100)"
    )
    
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    
    await scrape_and_save(
        company_ids=args.companies,
        max_jobs_per_company=args.limit
    )


if __name__ == "__main__":
    asyncio.run(main())
