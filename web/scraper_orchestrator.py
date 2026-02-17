"""
Scraper Orchestrator

Coordinates scraping across multiple companies based on user selection.
Dynamically imports and runs scrapers, normalizes results, and returns unified data.
"""

import asyncio
from typing import Dict, List, Any, Optional
import importlib
from pathlib import Path

from tools.scrapers.job_listing_normalizer import normalize_jobs
from utils.logging import get_logger

logger = get_logger(__name__)


class ScraperOrchestrator:
    """Orchestrate scraping across multiple companies."""
    
    # Map company IDs to scraper modules
    SCRAPER_MAP = {
        "netflix": "tools.scrapers.netflix",
        "meta": "tools.scrapers.meta",
        "samsung": "tools.scrapers.samsung",
        "vodafone": "tools.scrapers.vodafone",
        "rockstar": "tools.scrapers.rockstar",
        "rebellion": "tools.scrapers.rebellion",
        "miniclip": "tools.scrapers.miniclip",
        "google": "tools.scrapers.google",
        "ibm": "tools.scrapers.ibm",
    }
    
    async def scrape_companies(
        self, 
        company_ids: List[str],
        max_jobs_per_company: int = 100,
        discover_questions: bool = False
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Scrape jobs from selected companies.
        
        Args:
            company_ids: List of company IDs to scrape
            max_jobs_per_company: Maximum jobs to fetch per company
            discover_questions: If True, automatically discover application questions for each job
        
        Returns:
            Dictionary mapping company_id -> list of normalized jobs
        """
        results = {}
        
        # Run scrapers in parallel
        tasks = []
        for company_id in company_ids:
            if company_id not in self.SCRAPER_MAP:
                logger.warning(f"No scraper found for company: {company_id}")
                continue
            
            task = self._scrape_company(company_id, max_jobs_per_company)
            tasks.append(task)
        
        if tasks:
            scrape_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for company_id, result in zip(company_ids, scrape_results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to scrape {company_id}: {result}")
                    results[company_id] = []
                else:
                    results[company_id] = result
        
        total_jobs = sum(len(jobs) for jobs in results.values())
        logger.info(f"Scraped {total_jobs} jobs from {len(results)} companies")
        
        # Optionally discover questions for all scraped jobs
        if discover_questions and total_jobs > 0:
            logger.info("Starting automatic question discovery...")
            await self._discover_questions_for_results(results)
        
        return results
    
    async def _scrape_company(
        self, 
        company_id: str, 
        max_jobs: int
    ) -> List[Dict[str, Any]]:
        """Scrape a single company.
        
        Args:
            company_id: Company ID
            max_jobs: Maximum jobs to fetch
        
        Returns:
            List of normalized job dictionaries
        """
        try:
            module_name = self.SCRAPER_MAP[company_id]
            logger.info(f"Scraping {company_id} using {module_name}")
            
            # Dynamically import the scraper module
            scraper_module = importlib.import_module(module_name)
            
            # Call appropriate scraper function based on company
            raw_jobs = []
            
            # Netflix has specific function: scrape_netflix_jobs
            if company_id == "netflix" and hasattr(scraper_module, "scrape_netflix_jobs"):
                logger.info("Calling scrape_netflix_jobs (no database)")
                raw_jobs = await scraper_module.scrape_netflix_jobs(
                    location="United Kingdom",
                    save_to_db=False  # Don't save to database here
                )
            # Look for standard function names
            elif hasattr(scraper_module, "scrape_jobs"):
                raw_jobs = await scraper_module.scrape_jobs()
            elif hasattr(scraper_module, "scrape"):
                raw_jobs = await scraper_module.scrape()
            else:
                logger.warning(f"No scrape function found in {module_name}, trying main()")
                # Last resort: call main() but this might try to use database
                if hasattr(scraper_module, "main"):
                    raw_jobs = await scraper_module.main()
                else:
                    logger.error(f"No scrape function found in {module_name}")
                    return []
            
            # Limit results
            if len(raw_jobs) > max_jobs:
                raw_jobs = raw_jobs[:max_jobs]
            
            # Normalize jobs
            normalized = normalize_jobs(company_id, raw_jobs)
            
            # Convert to dicts
            normalized_dicts = [job.to_dict() for job in normalized]
            
            logger.info(f"Scraped {len(normalized_dicts)} jobs from {company_id}")
            return normalized_dicts
        
        except Exception as e:
            logger.error(f"Error scraping {company_id}: {e}", exc_info=True)
            return []
    
    async def _discover_questions_for_results(self, results: Dict[str, List[Dict[str, Any]]]) -> None:
        """Discover application questions for all scraped jobs.
        
        Args:
            results: Dictionary of company_id -> list of jobs
        """
        from web.question_discovery import QuestionDiscoveryService
        
        discovery_service = QuestionDiscoveryService()
        
        # Flatten all jobs
        all_jobs = []
        for company_id, jobs in results.items():
            for job in jobs:
                if job.get("job_url"):
                    all_jobs.append(job)
        
        if not all_jobs:
            logger.warning("No jobs with URLs found for question discovery")
            return
        
        logger.info(f"Discovering questions for {len(all_jobs)} jobs...")
        
        successful = 0
        failed = 0
        
        for idx, job in enumerate(all_jobs, 1):
            company = job.get("company", "Unknown")
            title = job.get("title", "Unknown")
            job_url = job.get("job_url")
            
            logger.info(f"  [{idx}/{len(all_jobs)}] {company} - {title[:50]}...")
            
            try:
                result = await discovery_service.discover_questions(
                    job_url=job_url,
                    company_name=company,
                    job_title=title
                )
                
                if result.get("success"):
                    logger.info(f"    ✓ Discovered {result.get('questions_count', 0)} questions")
                    successful += 1
                else:
                    logger.warning(f"    ✗ {result.get('error', 'Unknown error')}")
                    failed += 1
                
                # Delay to avoid rate limiting
                if idx < len(all_jobs):
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"    ✗ Error: {e}")
                failed += 1
        
        logger.info(f"Question discovery complete: {successful} successful, {failed} failed")


async def test_scraper():
    """Test the orchestrator."""
    orchestrator = ScraperOrchestrator()
    
    # Test with a single company
    results = await orchestrator.scrape_companies(["netflix"], max_jobs_per_company=5)
    
    for company, jobs in results.items():
        print(f"\n{company.upper()}: {len(jobs)} jobs")
        if jobs:
            print(f"Sample job: {jobs[0]['title']} - {jobs[0]['location']}")


if __name__ == "__main__":
    asyncio.run(test_scraper())
