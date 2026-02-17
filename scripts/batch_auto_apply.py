"""
Batch Auto-Apply Script

Automatically applies to multiple jobs from scraped JSON data.
Uses unified user profile to fill all application forms.

Usage:
    # Apply to all jobs in latest scraped JSON
    python scripts/batch_auto_apply.py --latest-json --profile data/profile.json
    
    # Apply to specific company
    python scripts/batch_auto_apply.py --latest-json --company netflix --profile data/profile.json
    
    # Dry-run mode (test without submitting)
    python scripts/batch_auto_apply.py --latest-json --profile data/profile.json --dry-run
    
    # Limit number of applications
    python scripts/batch_auto_apply.py --latest-json --limit 5 --profile data/profile.json
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

from utils.logging import configure_logging, get_logger
from agents.auto_apply.orchestrator import AutoApplyOrchestrator

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
            # Only include jobs with URLs
            if job.get("job_url"):
                jobs.append({
                    "company": job.get("company", company).title(),
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


def load_profile(profile_path: Path) -> Dict[str, Any]:
    """Load user profile.
    
    Args:
        profile_path: Path to profile JSON
        
    Returns:
        Profile dictionary
    """
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")
    
    with open(profile_path, "r") as f:
        return json.load(f)


async def apply_to_jobs(
    jobs: List[Dict[str, Any]],
    profile_path: Path,
    cv_path: Path = None,
    dry_run: bool = False,
    delay_between: int = 10
):
    """Apply to multiple jobs.
    
    Args:
        jobs: List of job dictionaries
        profile_path: Path to user profile JSON file
        cv_path: Path to CV file
        dry_run: If True, don't submit applications
        delay_between: Seconds to wait between applications
    """
    orchestrator = AutoApplyOrchestrator()
    
    results = {
        "successful": [],
        "failed": [],
        "skipped": []
    }
    
    for idx, job in enumerate(jobs, 1):
        company = job.get("company", "Unknown")
        title = job.get("title", "Unknown")
        job_url = job.get("job_url")
        
        logger.info("=" * 60)
        logger.info(f"[{idx}/{len(jobs)}] Applying to: {company} - {title}")
        logger.info(f"URL: {job_url}")
        logger.info("=" * 60)
        
        if not job_url:
            logger.warning("Skipping job without URL")
            results["skipped"].append({
                "company": company,
                "title": title,
                "reason": "no_url"
            })
            continue
        
        try:
            # Prepare paths
            cv_file = cv_path if cv_path else PROJECT_ROOT / "data" / "cv_library" / "sample_resume.txt"
            
            # Run auto-apply with inputs (use placeholder cover letter)
            result = await orchestrator.run_with_inputs_async(
                job_url=job_url,
                cover_letter="I am excited to apply for this position.",  # Placeholder cover letter
                profile_path=profile_path,
                cv_path=cv_file,
                wait_for_user=not dry_run  # Don't wait in dry-run mode
            )
            
            if result.get("success"):
                logger.info(f"✅ Successfully applied to {company} - {title}")
                results["successful"].append({
                    "company": company,
                    "title": title,
                    "job_url": job_url,
                    "timestamp": datetime.now().isoformat()
                })
            else:
                error = result.get("error", "Unknown error")
                logger.error(f"❌ Failed to apply: {error}")
                results["failed"].append({
                    "company": company,
                    "title": title,
                    "job_url": job_url,
                    "error": error,
                    "timestamp": datetime.now().isoformat()
                })
            
            # Delay between applications
            if idx < len(jobs):
                logger.info(f"Waiting {delay_between} seconds before next application...")
                await asyncio.sleep(delay_between)
        
        except Exception as e:
            logger.error(f"❌ Exception during application: {e}", exc_info=True)
            results["failed"].append({
                "company": company,
                "title": title,
                "job_url": job_url,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    return results


async def main():
    """Main execution."""
    parser = argparse.ArgumentParser(description="Batch auto-apply to multiple jobs")
    
    parser.add_argument(
        "--json",
        type=str,
        help="Path to scraped jobs JSON file"
    )
    
    parser.add_argument(
        "--latest-json",
        action="store_true",
        help="Use the latest scraped JSON file"
    )
    
    parser.add_argument(
        "--profile",
        type=str,
        required=True,
        help="Path to user profile JSON"
    )
    
    parser.add_argument(
        "--cv",
        type=str,
        help="Path to CV file (PDF recommended)"
    )
    
    parser.add_argument(
        "--company",
        type=str,
        help="Only apply to jobs from this company"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of applications to submit"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test mode - fill forms but don't submit"
    )
    
    parser.add_argument(
        "--delay",
        type=int,
        default=10,
        help="Seconds to wait between applications (default: 10)"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="data/batch_apply_results.json",
        help="Output file for results"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Batch Auto-Apply to Jobs")
    logger.info("=" * 60)
    
    # Load jobs
    if args.latest_json:
        json_file = find_latest_json()
        logger.info(f"Using latest JSON file: {json_file}")
    elif args.json:
        json_file = Path(args.json)
        if not json_file.is_absolute():
            json_file = PROJECT_ROOT / json_file
    else:
        logger.error("Must specify --json or --latest-json")
        return 1
    
    logger.info(f"\nStep 1: Loading jobs from {json_file}...")
    jobs = load_jobs_from_json(json_file)
    logger.info(f"✅ Loaded {len(jobs)} jobs with URLs")
    
    if not jobs:
        logger.error("No jobs with URLs found!")
        logger.error("Tip: Check if scraper extracted job URLs properly")
        return 1
    
    # Filter by company if specified
    if args.company:
        jobs = [j for j in jobs if j.get("company", "").lower() == args.company.lower()]
        logger.info(f"Filtered to {len(jobs)} jobs from {args.company}")
    
    # Apply limit
    if args.limit:
        jobs = jobs[:args.limit]
        logger.info(f"Limited to {len(jobs)} jobs")
    
    # Validate profile path
    logger.info(f"\nStep 2: Validating user profile at {args.profile}...")
    profile_path = Path(args.profile)
    if not profile_path.is_absolute():
        profile_path = PROJECT_ROOT / profile_path
    
    if not profile_path.exists():
        logger.error(f"Profile file not found: {profile_path}")
        return 1
    
    logger.info(f"✅ Found profile at {profile_path}")
    
    # Load CV if provided
    cv_path = None
    if args.cv:
        cv_path = Path(args.cv)
        if not cv_path.is_absolute():
            cv_path = PROJECT_ROOT / cv_path
        
        if not cv_path.exists():
            logger.warning(f"CV file not found: {cv_path}")
            cv_path = None
        else:
            logger.info(f"✅ Will upload CV: {cv_path}")
    
    # Confirm before starting
    logger.info("\n" + "=" * 60)
    logger.info("Ready to Apply")
    logger.info("=" * 60)
    logger.info(f"Jobs to apply: {len(jobs)}")
    logger.info(f"Mode: {'DRY-RUN (no submissions)' if args.dry_run else 'LIVE (will submit applications)'}")
    logger.info(f"Delay between applications: {args.delay} seconds")
    
    if not args.dry_run:
        logger.warning("\n⚠️  WARNING: This will submit real job applications!")
        response = input("\nType 'yes' to proceed: ")
        if response.lower() != "yes":
            logger.info("Cancelled by user")
            return 0
    
    # Apply to jobs
    logger.info("\nStep 3: Starting batch application process...")
    results = await apply_to_jobs(
        jobs=jobs,
        profile_path=profile_path,
        cv_path=cv_path,
        dry_run=args.dry_run,
        delay_between=args.delay
    )
    
    # Save results
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "dry_run": args.dry_run,
            "total_jobs": len(jobs),
            "results": results,
            "summary": {
                "successful": len(results["successful"]),
                "failed": len(results["failed"]),
                "skipped": len(results["skipped"])
            }
        }, f, indent=2)
    
    logger.info(f"\n✅ Saved results to: {output_path}")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Batch Application Complete")
    logger.info("=" * 60)
    logger.info(f"✅ Successful: {len(results['successful'])}")
    logger.info(f"❌ Failed: {len(results['failed'])}")
    logger.info(f"⏭️  Skipped: {len(results['skipped'])}")
    logger.info(f"Total processed: {len(jobs)}")
    
    if results["successful"]:
        logger.info("\nSuccessfully applied to:")
        for app in results["successful"][:10]:  # Show first 10
            logger.info(f"  • {app['company']} - {app['title']}")
        if len(results["successful"]) > 10:
            logger.info(f"  ... and {len(results['successful']) - 10} more")
    
    if results["failed"]:
        logger.warning("\nFailed applications:")
        for app in results["failed"][:5]:  # Show first 5
            logger.warning(f"  • {app['company']} - {app['title']}: {app['error']}")
        if len(results["failed"]) > 5:
            logger.warning(f"  ... and {len(results['failed']) - 5} more")
    
    logger.info("\n📋 Next Steps:")
    if args.dry_run:
        logger.info("  1. Review dry-run results")
        logger.info("  2. If all looks good, run again without --dry-run")
    else:
        logger.info("  1. Check answers/applied/ for submitted applications")
        logger.info("  2. Review answers/not_applied/ for failed attempts")
        logger.info("  3. Monitor your email for responses")
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
