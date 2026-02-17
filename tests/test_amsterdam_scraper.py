"""Test Netflix scraper with Amsterdam jobs + database integration."""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

from tools.scrapers.netflix import scrape_netflix_jobs

load_dotenv()


async def main():
    """Scrape Amsterdam jobs and save to database."""
    print("🔍 Scraping Netflix jobs for Amsterdam...\n")
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL not set")
        return
    
    # Scrape Amsterdam jobs and save to database
    jobs = await scrape_netflix_jobs(
        location="Berlin",
        save_to_db=True,
        db_connection_string=db_url
    )
    
    print(f"\n✅ Found {len(jobs)} Amsterdam jobs")
    
    if jobs:
        print("\nJobs scraped:")
        for i, job in enumerate(jobs, 1):
            print(f"{i}. {job.title}")
            print(f"   Location: {job.location}")
            print(f"   Department: {job.department}")
            print(f"   URL: {job.job_url}\n")
    
    print("✅ Done! Check DBeaver to see Amsterdam jobs in the database.")


if __name__ == "__main__":
    asyncio.run(main())
