"""
Scraper Orchestrator

Coordinates scraping across multiple companies based on user selection.
Dynamically imports and runs scrapers, normalizes results, and returns unified data.
"""

import asyncio
from typing import Dict, List, Any
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
        max_jobs_per_company: int = 100
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Scrape jobs from selected companies.
        
        Args:
            company_ids: List of company IDs to scrape
            max_jobs_per_company: Maximum jobs to fetch per company
        
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
            
            # Find the main scraping function (usually scrape_jobs)
            if hasattr(scraper_module, "scrape_jobs"):
                scrape_func = scraper_module.scrape_jobs
            elif hasattr(scraper_module, "main"):
                scrape_func = scraper_module.main
            else:
                logger.error(f"No scrape function found in {module_name}")
                return []
            
            # Call the scraper
            raw_jobs = await scrape_func()
            
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
