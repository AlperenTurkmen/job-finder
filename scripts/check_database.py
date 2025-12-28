"""Quick script to verify database contents."""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db_client import JobFinderDB
from utils.logging import get_logger

logger = get_logger(__name__)
load_dotenv()


async def main():
    """Check database contents."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("❌ DATABASE_URL not set")
        return
    
    db = JobFinderDB(db_url)
    await db.connect()
    
    try:
        async with db.pool.acquire() as conn:
            # Count companies
            company_count = await conn.fetchval("SELECT COUNT(*) FROM companies")
            logger.info(f"📊 Companies: {company_count}")
            
            # Count jobs
            job_count = await conn.fetchval("SELECT COUNT(*) FROM jobs")
            logger.info(f"📊 Jobs: {job_count}")
            
            # Show companies
            companies = await conn.fetch("SELECT id, name, domain FROM companies")
            for company in companies:
                logger.info(f"  • {company['name']} (ID: {company['id']})")
            
            # Show sample jobs
            jobs = await conn.fetch("""
                SELECT j.title, j.location, c.name as company
                FROM jobs j
                JOIN companies c ON j.company_id = c.id
                LIMIT 5
            """)
            logger.info("\n📋 Sample jobs:")
            for job in jobs:
                logger.info(f"  • {job['title']} at {job['company']} ({job['location']})")
    
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
