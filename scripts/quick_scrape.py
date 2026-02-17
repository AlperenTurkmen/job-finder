#!/usr/bin/env python3
"""
Quick Scrape & Discover Script

Scrapes jobs from companies and automatically discovers application questions.

Usage:
    python scripts/quick_scrape.py netflix meta google --limit 5
    python scripts/quick_scrape.py --all-companies --limit 10
"""

import asyncio
import argparse
import sys
import json
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web.scraper_orchestrator import ScraperOrchestrator
from utils.db_client import DatabaseClient
from utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

# Available companies
AVAILABLE_COMPANIES = {
    "netflix": "Netflix",
    "meta": "Meta",
    "samsung": "Samsung",
    "vodafone": "Vodafone",
    "rockstar": "Rockstar Games",
    "rebellion": "Rebellion",
    "miniclip": "Miniclip",
    "google": "Google",
    "ibm": "IBM",
}


async def scrape_and_discover(
    company_ids: list,
    max_jobs_per_company: int = 100,
    discover_questions: bool = True,
    save_to_db: bool = True
):
    """Scrape jobs and optionally discover questions.
    
    Args:
        company_ids: List of company IDs to scrape
        max_jobs_per_company: Maximum jobs per company
        discover_questions: Whether to discover application questions
        save_to_db: Whether to save jobs to database
    """
    logger.info("=" * 60)
    logger.info("Starting Job Scraping and Question Discovery")
    logger.info(f"Companies: {', '.join([AVAILABLE_COMPANIES.get(c, c) for c in company_ids])}")
    logger.info(f"Max jobs per company: {max_jobs_per_company}")
    logger.info(f"Discover questions: {discover_questions}")
    logger.info("=" * 60)
    
    # Scrape jobs
    orchestrator = ScraperOrchestrator()
    results = await orchestrator.scrape_companies(
        company_ids=company_ids,
        max_jobs_per_company=max_jobs_per_company,
        discover_questions=discover_questions
    )
    
    total_jobs = sum(len(jobs) for jobs in results.values())
    
    if total_jobs == 0:
        logger.warning("No jobs scraped!")
        return
    
    logger.info(f"\nTotal jobs scraped: {total_jobs}")
    for company_id, jobs in results.items():
        company_name = AVAILABLE_COMPANIES.get(company_id, company_id)
        logger.info(f"  {company_name}: {len(jobs)} jobs")
    
    # Save to database if requested and available
    if save_to_db:
        try:
            logger.info("\nAttempting to save jobs to database...")
            db = DatabaseClient()
            await db.initialize()
            
            saved_count = 0
            for company_results in results.values():
                for job in company_results:
                    try:
                        await db.insert_job(job)
                        saved_count += 1
                    except Exception as e:
                        logger.error(f"Failed to save job: {e}")
            
            await db.close()
            logger.info(f"✅ Saved {saved_count} jobs to database")
            
        except Exception as e:
            logger.warning(f"Database not available: {e}")
            logger.info("Saving to JSON files instead...")
            save_to_db = False
    
    # Save to JSON if database not available or as backup
    if not save_to_db or True:  # Always save JSON as backup
        from datetime import datetime
        output_dir = PROJECT_ROOT / "data" / "scraped_jobs"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        combined_file = output_dir / f"all_jobs_{timestamp}.json"
        
        with open(combined_file, "w") as f:
            json.dump({
                "scraped_at": datetime.now().isoformat(),
                "companies": [AVAILABLE_COMPANIES.get(c, c) for c in company_ids],
                "total_jobs": total_jobs,
                "jobs_by_company": results
            }, f, indent=2)
        
        logger.info(f"💾 Jobs also saved to: {combined_file}")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("COMPLETE!")
    logger.info("=" * 60)
    
    if discover_questions:
        questions_dir = PROJECT_ROOT / "data" / "application_questions"
        question_files = list(questions_dir.glob("*.json"))
        logger.info(f"\nQuestions saved to: {questions_dir}")
        logger.info(f"Total question files: {len(question_files)}")
        
        logger.info("\n📋 Next Steps:")
        logger.info("  1. View questions: python -m http.server 8080 (then visit /questions)")
        logger.info("     OR check files in: data/application_questions/")
        logger.info("  2. Run: python scripts/discover_all_questions.py --help")
        logger.info("  3. Download template from web UI or use data/user_answers_template.json")
        logger.info("  4. Fill out data/user_answers.json with your answers")
        logger.info("  5. Start auto-applying from the web interface!")
    else:
        logger.info("\n📋 Next Steps:")
        logger.info("  1. Run with --discover-questions to find application questions")
        logger.info("  2. Or use the web interface to browse jobs")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape jobs and discover application questions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape from Netflix and discover questions
  python scripts/quick_scrape.py netflix --limit 5
  
  # Scrape from multiple companies
  python scripts/quick_scrape.py netflix meta google --limit 10
  
  # Scrape all companies
  python scripts/quick_scrape.py --all-companies --limit 5
  
  # Scrape without discovering questions
  python scripts/quick_scrape.py netflix --no-discover-questions
        """
    )
    
    parser.add_argument(
        "companies",
        nargs="*",
        choices=list(AVAILABLE_COMPANIES.keys()),
        help="Company IDs to scrape (netflix, meta, samsung, etc.)"
    )
    
    parser.add_argument(
        "--all-companies",
        action="store_true",
        help="Scrape all available companies"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum jobs per company (default: 100)"
    )
    
    parser.add_argument(
        "--no-discover-questions",
        action="store_true",
        help="Skip automatic question discovery"
    )
    
    parser.add_argument(
        "--no-save-db",
        action="store_true",
        help="Don't save jobs to database"
    )
    
    parser.add_argument(
        "--list-companies",
        action="store_true",
        help="List available companies and exit"
    )
    
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    
    # List companies
    if args.list_companies:
        print("Available companies:")
        for company_id, company_name in AVAILABLE_COMPANIES.items():
            print(f"  {company_id:12} -> {company_name}")
        return
    
    # Determine which companies to scrape
    if args.all_companies:
        company_ids = list(AVAILABLE_COMPANIES.keys())
    elif args.companies:
        company_ids = args.companies
    else:
        print("Error: Must specify companies or --all-companies")
        print("\nExamples:")
        print("  python scripts/quick_scrape.py netflix meta")
        print("  python scripts/quick_scrape.py --all-companies --limit 5")
        print("\nUse --list-companies to see available options")
        sys.exit(1)
    
    # Run scraping and discovery
    await scrape_and_discover(
        company_ids=company_ids,
        max_jobs_per_company=args.limit,
        discover_questions=not args.no_discover_questions,
        save_to_db=not args.no_save_db
    )


if __name__ == "__main__":
    asyncio.run(main())
