"""Score jobs from the database using for_me and for_them agents.

This script:
1. Reads jobs from the database
2. Sends each job to the scoring agents
3. Updates the database with the scores
"""

import asyncio
import os
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.db_client import JobFinderDB
from utils.logging import get_logger
from agents.scoring.for_me_score_agent import ForMeScoreAgent
from agents.scoring.for_them_score_agent import ForThemScoreAgent

logger = get_logger(__name__)


async def score_jobs(limit: int = 5) -> List[Dict[str, Any]]:
    """Score jobs from the database and update scores.
    
    Args:
        limit: Maximum number of jobs to score
        
    Returns:
        List of scored jobs with results
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    db = JobFinderDB(db_url)
    await db.connect()
    
    # Initialize scoring agents
    for_me_agent = ForMeScoreAgent()
    for_them_agent = ForThemScoreAgent()
    
    results = []
    
    try:
        async with db.pool.acquire() as conn:
            # Get jobs with descriptions (those that have been scraped)
            jobs = await conn.fetch(
                """
                SELECT j.*, c.name as company_name
                FROM jobs j
                JOIN companies c ON j.company_id = c.id
                WHERE j.description IS NOT NULL
                ORDER BY j.created_at DESC
                LIMIT $1
                """,
                limit
            )
            
            if not jobs:
                logger.warning("No jobs with descriptions found in database")
                return []
            
            logger.info(f"Found {len(jobs)} jobs to score")
            
            for i, job in enumerate(jobs, 1):
                job_dict = dict(job)
                company_name = job_dict.pop("company_name")
                
                logger.info(f"\n[{i}/{len(jobs)}] Scoring: {job_dict['title']} at {company_name}")
                
                # Get raw job data for scoring
                job_title = job_dict.get("title", "Unknown Role")
                job_description = job_dict.get("description", "")
                job_location = job_dict.get("location")
                
                try:
                    # Get for_me score using raw job data
                    logger.info("  → Calling ForMeScoreAgent...")
                    for_me_result = for_me_agent.evaluate(
                        job_title=job_title,
                        job_description=job_description,
                        company=company_name,
                        location=job_location,
                    )
                    logger.info(f"  ✓ For-Me Score: {for_me_result.for_me_score:.0f}")
                    
                    # Get for_them score using raw job data
                    logger.info("  → Calling ForThemScoreAgent...")
                    for_them_result = for_them_agent.evaluate(
                        job_title=job_title,
                        job_description=job_description,
                        company=company_name,
                        location=job_location,
                    )
                    logger.info(f"  ✓ For-Them Score: {for_them_result.for_them_score:.0f}")
                    
                    # Update database
                    await db.update_job_scores(
                        job_url=job_dict["job_url"],
                        for_me_score=int(for_me_result.for_me_score),
                        for_them_score=int(for_them_result.for_them_score)
                    )
                    logger.info(f"  ✓ Database updated")
                    
                    results.append({
                        "title": job_dict["title"],
                        "company": company_name,
                        "for_me_score": for_me_result.for_me_score,
                        "for_me_reasoning": for_me_result.reasoning,
                        "for_me_dimensions": for_me_result.dimension_scores,
                        "for_them_score": for_them_result.for_them_score,
                        "for_them_reasoning": for_them_result.reasoning,
                        "for_them_dimensions": for_them_result.dimension_scores,
                    })
                    
                except Exception as e:
                    logger.error(f"  ✗ Failed to score job: {e}")
                    results.append({
                        "title": job_dict["title"],
                        "company": company_name,
                        "error": str(e)
                    })
    
    finally:
        await db.close()
    
    return results


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Score jobs from database")
    parser.add_argument("--limit", type=int, default=5, help="Number of jobs to score")
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("JOB SCORING PIPELINE")
    print("=" * 60)
    
    results = await score_jobs(limit=args.limit)
    
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    
    for r in results:
        if "error" in r:
            print(f"\n❌ {r['title']} @ {r['company']}")
            print(f"   Error: {r['error']}")
        else:
            print(f"\n✅ {r['title']} @ {r['company']}")
            print(f"   For-Me:   {r['for_me_score']:.0f}/100")
            print(f"   For-Them: {r['for_them_score']:.0f}/100")
            print(f"   Reasoning (Me):   {r['for_me_reasoning'][:100]}...")
            print(f"   Reasoning (Them): {r['for_them_reasoning'][:100]}...")
    
    print("\n" + "=" * 60)
    print(f"Scored {len([r for r in results if 'error' not in r])}/{len(results)} jobs successfully")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
