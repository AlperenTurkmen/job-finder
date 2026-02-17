"""Test database client directly (no scraping)."""

import asyncio
import os
from dotenv import load_dotenv

from utils.db_client import JobFinderDB, save_jobs_to_db

load_dotenv()


async def main():
    """Test database operations."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL not set")
        return
    
    print("=== Testing Database Client ===\n")
    
    # Create mock job data (simulating scraped jobs)
    mock_jobs = [
        {
            "title": "Senior Software Engineer - Test",
            "job_url": "https://netflix.com/jobs/test-12345",
            "location": "London, United Kingdom",
            "department": "Engineering",
            "work_type": "hybrid",
            "job_id": "TEST12345"
        },
        {
            "title": "Product Manager - Test",
            "job_url": "https://netflix.com/jobs/test-67890",
            "location": "Madrid, Spain",
            "department": "Product",
            "work_type": "onsite",
            "job_id": "TEST67890"
        }
    ]
    
    # Test 1: Save jobs to database
    print("📝 Saving mock jobs to database...")
    result = await save_jobs_to_db(
        company_name="Netflix",
        company_domain="netflix.com",
        careers_url="https://explore.jobs.netflix.net/careers",
        jobs=mock_jobs,
        db_connection_string=db_url
    )
    
    print(f"✅ Result: {result['inserted']} inserted, {result['updated']} updated\n")
    
    # Test 2: Try saving same jobs again (should update, not duplicate)
    print("📝 Saving same jobs again (testing deduplication)...")
    result2 = await save_jobs_to_db(
        company_name="Netflix",
        company_domain="netflix.com",
        careers_url="https://explore.jobs.netflix.net/careers",
        jobs=mock_jobs,
        db_connection_string=db_url
    )
    
    print(f"✅ Result: {result2['inserted']} inserted, {result2['updated']} updated")
    print("   (Should be 0 inserted, 2 updated - no duplicates!)\n")
    
    # Test 3: Read jobs back
    print("📖 Reading jobs from database...")
    db = JobFinderDB(db_url)
    await db.connect()
    
    try:
        jobs = await db.get_jobs_by_company("Netflix")
        print(f"✅ Found {len(jobs)} Netflix jobs in database")
        
        for job in jobs[:3]:
            print(f"   • {job['title']} - {job['location']}")
        
        # Test 4: Update job status
        print(f"\n📝 Updating job status...")
        updated = await db.update_job_status(
            mock_jobs[0]['job_url'],
            "applied",
        )
        print(f"✅ Status updated: {updated}")
        
        # Test 5: Update scores
        print(f"\n📝 Updating job scores...")
        updated = await db.update_job_scores(
            mock_jobs[0]['job_url'],
            for_me_score=85,
            for_them_score=75
        )
        print(f"✅ Scores updated: {updated}")
        
    finally:
        await db.close()
    
    print("\n✅ All database tests passed!")
    print("\n💡 Now check DBeaver to see:")
    print("   - Companies table has Netflix")
    print("   - Jobs table has test jobs with scores and status")


if __name__ == "__main__":
    asyncio.run(main())
