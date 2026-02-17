"""Quick test of Netflix scraper URL extraction."""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.scrapers.netflix import scrape_netflix_jobs


async def test():
    """Test Netflix scraper."""
    print("Testing Netflix scraper...")
    
    jobs = await scrape_netflix_jobs(
        location="London, United Kingdom",
        headless=True,
        save_to_db=False
    )
    
    # Limit to first 3 for testing
    jobs = jobs[:3]
    
    print(f"\nScraped {len(jobs)} jobs (showing first 3)")
    
    for i, job in enumerate(jobs, 1):
        # NetflixJobListing is a dataclass, access attributes not dict keys
        print(f"\n{i}. {job.title}")
        print(f"   Location: {job.location}")
        print(f"   URL: {job.job_url if job.job_url else 'MISSING'}")
        print(f"   Job ID: {job.job_id if job.job_id else 'MISSING'}")
    
    # Check if URLs were extracted
    urls_extracted = sum(1 for job in jobs if job.job_url)
    print(f"\n✅ {urls_extracted}/{len(jobs)} jobs have URLs")
    
    if urls_extracted == 0:
        print("❌ URL extraction failed!")
        return 1
    else:
        print("✅ URL extraction working!")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(test()))
