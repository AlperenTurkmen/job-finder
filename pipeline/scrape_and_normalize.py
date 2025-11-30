"""Pipeline: Scrape job URLs and normalize to structured JSON.

This script:
1. Reads a CSV file containing job URLs (with a 'url' column)
2. Scrapes each URL using the job scraper agent to extract raw text
3. Creates an intermediate CSV with 'raw_text' column
4. Passes that to the role_normaliser_agent to convert to structured JSON
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.role_normaliser_agent import run_agent as run_normaliser, ConversionResult
from job_scraper_agent import JobScraperAgent, BrowserMCPError, BrowserMCPTimeoutError, URLValidationError
from browser_client import _fetch_with_retry, BrowserMCPConfig
from content_cleaner import clean_job_content
from logging_utils import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "job_urls"
DEFAULT_INTERMEDIATE_DIR = PROJECT_ROOT / "data" / "roles_for_llm"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "roles"


async def scrape_urls_to_csv(
    input_csv: Path,
    output_csv: Path,
    *,
    timeout: float | None = None,
    clean_with_llm: bool = True,
    max_urls: int | None = None,
) -> tuple[int, int]:
    """Scrape job URLs and create a CSV with raw_text column.
    
    Args:
        input_csv: CSV file with 'url' column
        output_csv: Output CSV with 'raw_text' column
        timeout: Timeout for each scrape in seconds
        clean_with_llm: Whether to clean content with LLM
        max_urls: Maximum number of URLs to process
    
    Returns:
        Tuple of (successful_count, failed_count)
    """
    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")
    
    # Read URLs from input CSV
    urls: List[str] = []
    skipped_invalid = 0
    with input_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "url" not in (reader.fieldnames or []):
            raise ValueError("Input CSV must contain a 'url' column")
        
        for row in reader:
            url = row.get("url", "").strip()
            if not url:
                continue
            if not url.startswith(("http://", "https://")):
                skipped_invalid += 1
                continue
            urls.append(url)
            if max_urls is not None and len(urls) >= max_urls:
                break
    
    if not urls:
        raise ValueError("No URLs found in input CSV")
    
    logger.info(f"Found {len(urls)} URLs to scrape")
    if skipped_invalid:
        logger.info("Skipped %d malformed URLs (missing http/https)", skipped_invalid)
    
    # Scrape each URL and collect raw text
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    successful = 0
    failed = 0
    
    # Configure browser
    config = BrowserMCPConfig.from_env()
    if timeout is not None:
        config = BrowserMCPConfig(
            endpoint=config.endpoint,
            api_key=config.api_key,
            project=config.project,
            timeout=timeout,
        )
    
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["url", "raw_text", "status"])
        writer.writeheader()
        
        for idx, url in enumerate(urls, start=1):
            logger.info(f"[{idx}/{len(urls)}] Scraping {url}")
            
            try:
                # Scrape the URL using async browser client
                raw_content = await _fetch_with_retry(url, config)
                
                # Optionally clean with LLM
                if clean_with_llm:
                    logger.info(f"[{idx}/{len(urls)}] Cleaning content with LLM...")
                    raw_text = clean_job_content(raw_content, url)
                else:
                    raw_text = raw_content
                
                writer.writerow({
                    "url": url,
                    "raw_text": raw_text,
                    "status": "success"
                })
                successful += 1
                logger.info(f"[{idx}/{len(urls)}] Successfully scraped {len(raw_text)} characters")
                
            except (BrowserMCPTimeoutError, BrowserMCPError) as exc:
                logger.error(f"[{idx}/{len(urls)}] Failed to scrape {url}: {exc}")
                writer.writerow({
                    "url": url,
                    "raw_text": "",
                    "status": f"failed: {type(exc).__name__}"
                })
                failed += 1
                
            except Exception as exc:
                logger.exception(f"[{idx}/{len(urls)}] Unexpected error scraping {url}")
                writer.writerow({
                    "url": url,
                    "raw_text": "",
                    "status": f"failed: {type(exc).__name__}"
                })
                failed += 1
    
    logger.info(f"Scraping complete: {successful} successful, {failed} failed")
    logger.info(f"Intermediate CSV saved to {output_csv}")
    
    return successful, failed


def _load_mock_normalized_payloads(path: Path) -> Dict[str, Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping: Dict[str, Dict[str, Any]] = {}
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            key = item.get("job_url") or item.get("job_id")
            if key:
                mapping[str(key)] = item
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                mapping[str(key)] = value
    return mapping


def _apply_mock_normalization(
    intermediate_csv: Path,
    output_dir: Path,
    *,
    mock_json: Path,
) -> List[ConversionResult]:
    logger.info("Using mock normalized payloads from %s", mock_json)
    payloads = _load_mock_normalized_payloads(mock_json)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: List[ConversionResult] = []
    with intermediate_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=1):
            if (row.get("status") or "").lower() != "success":
                continue
            url = (row.get("url") or row.get("job_url") or "").strip()
            payload = payloads.get(url) or payloads.get(row.get("job_id", ""))
            if not payload:
                logger.warning("No mock payload found for %s", url)
                continue
            job_id = payload.get("job_id") or f"mock-role-{index:02d}"
            destination = output_dir / f"{job_id}.json"
            destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            results.append(
                ConversionResult(
                    index=index,
                    prompt="mock-normalizer",
                    output_path=destination,
                    payload=payload,
                    status="mock",
                )
            )
    return results


async def run_full_pipeline(
    input_csv: Path,
    *,
    intermediate_csv: Path | None = None,
    output_dir: Path,
    scrape_timeout: float | None = None,
    clean_with_llm: bool = True,
    max_urls: int | None = None,
    model: str = "gemini-2.0-flash-exp",
    temperature: float = 0.0,
    prompt_path: Path | None = None,
    example_path: Path | None = None,
    overwrite: bool = False,
    mock_normalized_json: Path | None = None,
) -> tuple[int, int, List[ConversionResult]]:
    """Run the full scrape + normalize pipeline.
    
    Returns:
        Tuple of (scraped_count, failed_count, normalization_results)
    """
    # Step 1: Scrape URLs to intermediate CSV
    if intermediate_csv is None:
        intermediate_csv = DEFAULT_INTERMEDIATE_DIR / f"{input_csv.stem}_scraped.csv"
    
    logger.info("=" * 80)
    logger.info("STEP 1: Scraping job URLs")
    logger.info("=" * 80)
    
    successful, failed = await scrape_urls_to_csv(
        input_csv,
        intermediate_csv,
        timeout=scrape_timeout,
        clean_with_llm=clean_with_llm,
        max_urls=max_urls,
    )
    
    if successful == 0:
        raise RuntimeError("No URLs were successfully scraped")
    
    # Step 2: Normalize to structured JSON
    logger.info("")
    logger.info("=" * 80)
    logger.info("STEP 2: Normalizing raw text to structured JSON")
    logger.info("=" * 80)
    
    if mock_normalized_json:
        results = _apply_mock_normalization(intermediate_csv, output_dir, mock_json=mock_normalized_json)
    else:
        results = run_normaliser(
            intermediate_csv,
            prompt_path=prompt_path,
            example_path=example_path,
            output_dir=output_dir,
            model=model,
            temperature=temperature,
            max_rows=None,  # Process all successfully scraped URLs
            overwrite=overwrite,
        )
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Scraped: {successful} successful, {failed} failed")
    logger.info(f"Normalized: {len(results)} roles")
    
    # Print status summary
    status_counts = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
    
    logger.info("Normalization status breakdown:")
    for status, count in sorted(status_counts.items()):
        logger.info(f"  {status}: {count}")
    
    return successful, failed, results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape job URLs and normalize to structured JSON"
    )
    parser.add_argument(
        "input_csv",
        type=Path,
        help="Input CSV file with 'url' column containing job posting URLs"
    )
    parser.add_argument(
        "--intermediate-csv",
        type=Path,
        help="Path for intermediate CSV with scraped raw_text (default: auto-generated)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for structured JSON output (default: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--scrape-timeout",
        type=float,
        default=60.0,
        help="Timeout in seconds for each scrape operation (default: 60.0)"
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Disable LLM-based content cleaning during scraping"
    )
    parser.add_argument(
        "--max-urls",
        type=int,
        help="Maximum number of URLs to process (for testing)"
    )
    parser.add_argument(
        "--model",
        default="gemini-2.0-flash-exp",
        help="Gemini model for normalization (default: gemini-2.0-flash-exp)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="LLM temperature for normalization (default: 0.0)"
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        help="Custom prompt template for normalization"
    )
    parser.add_argument(
        "--example-json",
        type=Path,
        help="Example JSON file for normalization prompt"
    )
    parser.add_argument(
        "--mock-normalized-json",
        type=Path,
        help="Path to a JSON file with precomputed normalized payloads (bypasses the LLM conversion step)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing JSON files in output directory"
    )
    
    args = parser.parse_args()
    
    try:
        import asyncio
        successful, failed, results = asyncio.run(run_full_pipeline(
            args.input_csv,
            intermediate_csv=args.intermediate_csv,
            output_dir=args.output_dir,
            scrape_timeout=args.scrape_timeout,
            clean_with_llm=not args.no_clean,
            max_urls=args.max_urls,
            model=args.model,
            temperature=args.temperature,
            prompt_path=args.prompt_file,
            example_path=args.example_json,
            overwrite=args.overwrite,
            mock_normalized_json=args.mock_normalized_json,
        ))
        
        # Print output file paths
        print("\nGenerated JSON files:")
        for result in results:
            print(f"  {result.output_path}")
        
        return 0 if failed == 0 else 1
        
    except Exception as exc:
        logger.exception("Pipeline failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
