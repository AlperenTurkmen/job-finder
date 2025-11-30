"""Complete end-to-end pipeline: Companies CSV → Job URLs → Scraped Content → Normalized JSON

This pipeline orchestrates:
1. Extract job URLs from company careers pages (job_url_extractor_agent)
2. Scrape and normalize those URLs (scrape_and_normalize pipeline)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.job_url_extractor_agent import extract_all_job_urls
from pipeline.scrape_and_normalize import run_full_pipeline
from logging_utils import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


DEFAULT_COMPANIES_CSV = PROJECT_ROOT / "data" / "companies" / "example_companies.csv"
DEFAULT_JOB_URLS_CSV = PROJECT_ROOT / "data" / "job_urls" / "sample_urls.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "roles"


async def run_complete_pipeline(
    companies_csv: Path,
    job_urls_csv: Path,
    output_dir: Path,
    *,
    url_extraction_model: str = "gemini-2.0-flash-exp",
    url_extraction_timeout: int = 60000,
    max_companies: int | None = None,
    scrape_timeout: float = 60.0,
    clean_with_llm: bool = True,
    max_urls: int | None = None,
    normalization_model: str = "gemini-2.0-flash-exp",
    temperature: float = 0.0,
    prompt_path: Path | None = None,
    example_path: Path | None = None,
    overwrite: bool = False,
) -> None:
    """Run the complete pipeline from companies to normalized JSON roles.
    
    Args:
        companies_csv: Input CSV with company names and careers page URLs
        job_urls_csv: Intermediate CSV for job URLs (will be created/appended)
        output_dir: Output directory for normalized JSON files
        url_extraction_model: Gemini model for URL extraction
        url_extraction_timeout: Timeout for page loading during URL extraction
        max_companies: Limit number of companies to process
        scrape_timeout: Timeout for scraping individual job pages
        clean_with_llm: Whether to clean scraped content with LLM
        max_urls: Limit number of URLs to scrape
        normalization_model: Gemini model for normalization
        temperature: LLM temperature for normalization
        prompt_path: Custom prompt for normalization
        example_path: Example JSON for normalization
        overwrite: Overwrite existing JSON files
    """
    logger.info("=" * 80)
    logger.info("COMPLETE PIPELINE: COMPANIES → JOB URLs → SCRAPED → NORMALIZED JSON")
    logger.info("=" * 80)
    
    # Step 1: Extract job URLs from company careers pages
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 1: Extracting job URLs from company careers pages")
    logger.info("=" * 80)
    
    extraction_results = await extract_all_job_urls(
        companies_csv,
        job_urls_csv,
        model=url_extraction_model,
        timeout=url_extraction_timeout,
        max_companies=max_companies
    )
    
    success_count = sum(1 for r in extraction_results if r.status == "success")
    if success_count == 0:
        raise RuntimeError("No job URLs were successfully extracted")
    
    # Step 2: Scrape and normalize job URLs
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 2: Scraping and normalizing job postings")
    logger.info("=" * 80)
    
    intermediate_csv = PROJECT_ROOT / "data" / "roles_for_llm" / f"{job_urls_csv.stem}_scraped.csv"
    
    scraped_count, failed_count, normalization_results = await run_full_pipeline(
        job_urls_csv,
        intermediate_csv=intermediate_csv,
        output_dir=output_dir,
        scrape_timeout=scrape_timeout,
        clean_with_llm=clean_with_llm,
        max_urls=max_urls,
        model=normalization_model,
        temperature=temperature,
        prompt_path=prompt_path,
        example_path=example_path,
        overwrite=overwrite,
    )
    
    # Final summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("COMPLETE PIPELINE SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Companies processed: {len(extraction_results)}")
    logger.info(f"Job URLs extracted: {sum(len(r.job_urls) for r in extraction_results)}")
    logger.info(f"Job pages scraped: {scraped_count} successful, {failed_count} failed")
    logger.info(f"JSON roles created: {len(normalization_results)}")
    logger.info(f"Output directory: {output_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Complete pipeline: Companies → Job URLs → Scraped Content → Normalized JSON"
    )
    
    # Input/Output
    parser.add_argument(
        "--companies-csv",
        type=Path,
        default=DEFAULT_COMPANIES_CSV,
        help=f"Input CSV with company names and careers URLs (default: {DEFAULT_COMPANIES_CSV})"
    )
    parser.add_argument(
        "--job-urls-csv",
        type=Path,
        default=DEFAULT_JOB_URLS_CSV,
        help=f"Intermediate CSV for job URLs (default: {DEFAULT_JOB_URLS_CSV})"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for normalized JSON (default: {DEFAULT_OUTPUT_DIR})"
    )
    
    # Step 1: URL Extraction Options
    url_group = parser.add_argument_group("URL Extraction Options")
    url_group.add_argument(
        "--url-extraction-model",
        default="gemini-2.0-flash-exp",
        help="Gemini model for URL extraction (default: gemini-2.0-flash-exp)"
    )
    url_group.add_argument(
        "--url-extraction-timeout",
        type=int,
        default=60000,
        help="Page load timeout in ms for URL extraction (default: 60000)"
    )
    url_group.add_argument(
        "--max-companies",
        type=int,
        help="Limit number of companies to process (for testing)"
    )
    
    # Step 2: Scraping Options
    scrape_group = parser.add_argument_group("Scraping Options")
    scrape_group.add_argument(
        "--scrape-timeout",
        type=float,
        default=60.0,
        help="Timeout per job page scrape in seconds (default: 60.0)"
    )
    scrape_group.add_argument(
        "--no-clean",
        action="store_true",
        help="Disable LLM-based content cleaning during scraping"
    )
    scrape_group.add_argument(
        "--max-urls",
        type=int,
        help="Limit number of job URLs to scrape (for testing)"
    )
    
    # Step 3: Normalization Options
    norm_group = parser.add_argument_group("Normalization Options")
    norm_group.add_argument(
        "--normalization-model",
        default="gemini-2.0-flash-exp",
        help="Gemini model for normalization (default: gemini-2.0-flash-exp)"
    )
    norm_group.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="LLM temperature for normalization (default: 0.0)"
    )
    norm_group.add_argument(
        "--prompt-file",
        type=Path,
        help="Custom prompt template for normalization"
    )
    norm_group.add_argument(
        "--example-json",
        type=Path,
        help="Example JSON for normalization prompt"
    )
    norm_group.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing JSON files"
    )
    
    args = parser.parse_args()
    
    try:
        asyncio.run(
            run_complete_pipeline(
                args.companies_csv,
                args.job_urls_csv,
                args.output_dir,
                url_extraction_model=args.url_extraction_model,
                url_extraction_timeout=args.url_extraction_timeout,
                max_companies=args.max_companies,
                scrape_timeout=args.scrape_timeout,
                clean_with_llm=not args.no_clean,
                max_urls=args.max_urls,
                normalization_model=args.normalization_model,
                temperature=args.temperature,
                prompt_path=args.prompt_file,
                example_path=args.example_json,
                overwrite=args.overwrite,
            )
        )
        return 0
    except Exception as exc:
        logger.exception("Complete pipeline failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
