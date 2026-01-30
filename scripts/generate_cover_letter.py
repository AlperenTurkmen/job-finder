"""Generate a cover letter for a job from the database."""

import asyncio
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.db_client import JobFinderDB
from utils.logging import get_logger
from agents.cover_letter.cover_letter_generator_agent import CoverLetterGeneratorAgent
from agents.cover_letter.hr_simulation_agent import HRSimulationAgent

logger = get_logger(__name__)


async def generate_cover_letter(job_id: int = None):
    """Generate a cover letter for a job from the database.
    
    Args:
        job_id: Specific job ID, or None to use the highest-scored job
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    db = JobFinderDB(db_url)
    await db.connect()
    
    try:
        async with db.pool.acquire() as conn:
            if job_id:
                job = await conn.fetchrow(
                    """
                    SELECT j.*, c.name as company_name
                    FROM jobs j
                    JOIN companies c ON j.company_id = c.id
                    WHERE j.id = $1
                    """,
                    job_id
                )
            else:
                # Get highest scored job
                job = await conn.fetchrow(
                    """
                    SELECT j.*, c.name as company_name
                    FROM jobs j
                    JOIN companies c ON j.company_id = c.id
                    WHERE j.description IS NOT NULL
                      AND j.for_me_score IS NOT NULL
                    ORDER BY (j.for_me_score + j.for_them_score) DESC
                    LIMIT 1
                    """
                )
            
            if not job:
                logger.error("No suitable job found")
                return None
            
            job = dict(job)
            company = job.pop("company_name")
            
            logger.info(f"Generating cover letter for: {job['title']} at {company}")
            logger.info(f"Scores: For-Me={job.get('for_me_score')}, For-Them={job.get('for_them_score')}")
            
            # Generate cover letter
            generator = CoverLetterGeneratorAgent()
            letter = generator.generate(
                job_title=job["title"],
                job_description=job.get("description", ""),
                company=company,
                location=job.get("location"),
            )
            
            print("\n" + "=" * 60)
            print("GENERATED COVER LETTER")
            print("=" * 60)
            print(letter)
            print("=" * 60)
            
            # Optionally evaluate with HR agent
            hr_agent = HRSimulationAgent()
            feedback = hr_agent.evaluate(
                cover_letter=letter,
                job_title=job["title"],
                job_description=job.get("description", ""),
                company=company,
            )
            
            print("\n" + "=" * 60)
            print("HR EVALUATION")
            print("=" * 60)
            print(f"Score: {feedback.get('score', 'N/A')}/100")
            print(f"\nPositives:")
            for p in feedback.get("positives", []):
                print(f"  ✓ {p}")
            print(f"\nNegatives:")
            for n in feedback.get("negatives", []):
                print(f"  ✗ {n}")
            print(f"\nSuggestions:")
            for s in feedback.get("fix_suggestions", []):
                print(f"  → {s}")
            print("=" * 60)
            
            return letter
    
    finally:
        await db.close()


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate cover letter for a job")
    parser.add_argument("--job-id", type=int, help="Specific job ID (default: highest scored)")
    args = parser.parse_args()
    
    await generate_cover_letter(job_id=args.job_id)


if __name__ == "__main__":
    asyncio.run(main())
