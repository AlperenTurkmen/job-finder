"""
Automated Question Discovery Script

Automatically discovers application questions for all jobs.
Works with both database jobs and scraped JSON files.

Usage:
    # From database
    python scripts/discover_all_questions.py --company netflix
    python scripts/discover_all_questions.py --all
    
    # From JSON file
    python scripts/discover_all_questions.py --json data/scraped_jobs/all_jobs_*.json
    
    # From latest scraped JSON (no database needed)
    python scripts/discover_all_questions.py --latest-json
    
    python scripts/discover_all_questions.py --limit 10
"""

import asyncio
import argparse
import sys
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.db_client import DatabaseClient
from web.question_discovery import QuestionDiscoveryService
from utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


def load_jobs_from_json(json_path: Path) -> List[Dict[str, Any]]:
    """Load jobs from a scraped JSON file.
    
    Args:
        json_path: Path to JSON file
        
    Returns:
        List of job dictionaries
    """
    with open(json_path, "r") as f:
        data = json.load(f)
    
    jobs = []
    jobs_by_company = data.get("jobs_by_company", {})
    
    for company, company_jobs in jobs_by_company.items():
        for job in company_jobs:
            # Normalize job structure
            jobs.append({
                "company": job.get("company", company),
                "title": job.get("title", ""),
                "job_url": job.get("job_url", ""),
                "location": job.get("location", ""),
                "source": "json"
            })
    
    return jobs


def find_latest_json() -> Path:
    """Find the latest scraped jobs JSON file.
    
    Returns:
        Path to latest JSON file
    """
    scraped_dir = PROJECT_ROOT / "data" / "scraped_jobs"
    
    if not scraped_dir.exists():
        raise FileNotFoundError(f"Scraped jobs directory not found: {scraped_dir}")
    
    json_files = list(scraped_dir.glob("all_jobs_*.json"))
    
    if not json_files:
        raise FileNotFoundError(f"No scraped job files found in {scraped_dir}")
    
    # Sort by modification time, newest first
    latest = max(json_files, key=lambda p: p.stat().st_mtime)
    
    return latest


async def discover_questions_for_jobs(
    company_filter: str = None,
    limit: int = None,
    skip_existing: bool = True,
    json_file: Path = None,
    use_latest_json: bool = False
):
    """Discover questions for jobs from database or JSON file.
    
    Args:
        company_filter: Only process jobs from this company (optional)
        limit: Maximum number of jobs to process (optional)
        skip_existing: Skip jobs that already have discovered questions
        json_file: Load jobs from JSON file instead of database
        use_latest_json: Use the latest scraped JSON file
    """
    discovery_service = QuestionDiscoveryService()
    
    # Determine job source
    if use_latest_json:
        json_file = find_latest_json()
        logger.info(f"Using latest JSON file: {json_file}")
    
    if json_file:
        # Load from JSON
        logger.info(f"Loading jobs from JSON: {json_file}")
        jobs = load_jobs_from_json(json_file)
        logger.info(f"Loaded {len(jobs)} jobs from JSON")
        
        # Apply company filter
        if company_filter:
            jobs = [j for j in jobs if j.get("company", "").lower() == company_filter.lower()]
            logger.info(f"Filtered to {len(jobs)} jobs from {company_filter}")
        
    else:
        # Load from database
        db = DatabaseClient()
        try:
            await db.initialize()
            
            # Get all jobs from database
            if company_filter:
                logger.info(f"Fetching jobs from {company_filter}...")
                jobs = await db.get_jobs_by_companies([company_filter])
            else:
                logger.info("Fetching all jobs from database...")
                # Get all jobs - query all known companies
                all_jobs = []
                companies = ["Netflix", "Meta", "Samsung", "Vodafone", "Rockstar Games", 
                            "Rebellion", "Miniclip", "Google", "IBM"]
                for company in companies:
                    company_jobs = await db.get_jobs_by_companies([company])
                    all_jobs.extend(company_jobs)
                jobs = all_jobs
        except Exception as e:
            logger.error(f"Database error: {e}")
            logger.info("Tip: Use --latest-json to work without database")
            return
        finally:
            if db:
                await db.close()
    
    if not jobs:
        logger.warning("No jobs found")
        return
        
        logger.info(f"Found {len(jobs)} jobs to process")
        
        # Apply limit if specified
        if limit:
            jobs = jobs[:limit]
            logger.info(f"Limited to {len(jobs)} jobs")
        
        # Filter out jobs that already have discovered questions
        if skip_existing:
            all_discovered = discovery_service.get_all_questions()
            discovered_urls = {q["job_url"] for q in all_discovered}
            
            jobs_to_process = []
            for job in jobs:
                if job.get("job_url") not in discovered_urls:
                    jobs_to_process.append(job)
                else:
                    logger.debug(f"Skipping {job.get('title')} - questions already discovered")
            
            logger.info(f"{len(jobs_to_process)} jobs need question discovery (skipped {len(jobs) - len(jobs_to_process)})")
            jobs = jobs_to_process
        
        if not jobs:
            logger.info("No jobs to process (all have questions already discovered)")
            return
        
        # Discover questions for each job
        successful = 0
        failed = 0
        
        for idx, job in enumerate(jobs, 1):
            company = job.get("company", "Unknown")
            title = job.get("title", "Unknown")
            job_url = job.get("job_url")
            
            if not job_url:
                logger.warning(f"[{idx}/{len(jobs)}] Skipping job without URL: {title}")
                failed += 1
                continue
            
            logger.info(f"[{idx}/{len(jobs)}] Discovering questions for: {company} - {title}")
            
            try:
                result = await discovery_service.discover_questions(
                    job_url=job_url,
                    company_name=company,
                    job_title=title
                )
                
                if result.get("success"):
                    logger.info(f"  ✓ Discovered {result.get('questions_count', 0)} questions")
                    successful += 1
                else:
                    logger.warning(f"  ✗ Failed: {result.get('error', 'Unknown error')}")
                    failed += 1
                
                # Add delay between requests to avoid rate limiting
                if idx < len(jobs):
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"  ✗ Error: {e}", exc_info=True)
                failed += 1
        
        # Summary
        logger.info("=" * 60)
        logger.info(f"Question Discovery Complete")
        logger.info(f"  Successful: {successful}")
        logger.info(f"  Failed: {failed}")
        logger.info(f"  Total processed: {successful + failed}")
        logger.info("=" * 60)
        
        # Show unique questions summary
        unique_questions = discovery_service.get_unique_questions()
        logger.info(f"Total unique questions across all jobs: {len(unique_questions)}")
        
        # Suggest next steps
        logger.info("\nNext steps:")
        logger.info("  1. Merge questions: python scripts/merge_all_questions.py")
        logger.info("  2. Extract from CV: python scripts/extract_from_cv.py --cv your_cv.pdf")
        logger.info("  3. Fill remaining fields manually")
        logger.info("  4. Start auto-applying!")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Automatically discover application questions for jobs"
    )
    
    parser.add_argument(
        "--company",
        type=str,
        help="Only process jobs from this company (e.g., 'Netflix', 'Meta')"
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all jobs in database"
    )
    
    parser.add_argument(
        "--json",
        type=str,
        help="Load jobs from JSON file instead of database"
    )
    
    parser.add_argument(
        "--latest-json",
        action="store_true",
        help="Use the latest scraped JSON file (no database needed)"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of jobs to process"
    )
    
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-discover questions even if they already exist"
    )
    
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    
    # Validate arguments
    if not args.all and not args.company and not args.json and not args.latest_json:
        print("Error: Must specify job source")
        print("Examples:")
        print("  # From database:")
        print("  python scripts/discover_all_questions.py --company Netflix")
        print("  python scripts/discover_all_questions.py --all --limit 5")
        print("")
        print("  # From JSON file (no database needed):")
        print("  python scripts/discover_all_questions.py --latest-json")
        print("  python scripts/discover_all_questions.py --json data/scraped_jobs/all_jobs_*.json")
        sys.exit(1)
    
    logger.info("Starting automated question discovery...")
    
    # Prepare JSON file path if provided
    json_file = None
    if args.json:
        json_file = Path(args.json)
        if not json_file.is_absolute():
            json_file = PROJECT_ROOT / json_file
    
    await discover_questions_for_jobs(
        company_filter=args.company,
        limit=args.limit,
        skip_existing=not args.no_skip_existing,
        json_file=json_file,
        use_latest_json=args.latest_json
    )


if __name__ == "__main__":
    asyncio.run(main())
