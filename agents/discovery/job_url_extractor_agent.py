"""Agent that extracts individual job posting URLs from company careers pages.

This agent:
1. Reads companies and their careers page URLs from a CSV
2. Uses Playwright to visit each careers page
3. Extracts all links from the page
4. Uses LLM to filter for actual job posting URLs
5. Appends the job URLs to a CSV file
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set

import google.generativeai as genai
import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")

from utils.logging import configure_logging, get_logger
from tools.duckduckgo_search import duckduckgo_search
from tools.google_search import google_search
from agents.discovery.careers_page_finder_agent import choose_careers_page

try:  # pragma: no cover - optional helper
    from utils.mock_llm import get_mock_response
except Exception:  # pragma: no cover - fallback when module missing
    def get_mock_response(*_, **__):  # type: ignore
        return None

configure_logging()
logger = get_logger(__name__)


@dataclass(slots=True)
class CompanyInfo:
    """Company name and their careers page URL."""
    name: str
    careers_url: str | None


@dataclass(slots=True)
class ExtractionResult:
    """Result of extracting job URLs from a company's careers page."""
    company: str
    careers_url: str
    job_urls: List[str]
    status: str
    error: str | None = None


FILTER_PROMPT = """You are helping me identify actual job posting URLs from a list of links extracted from a company's careers page.

Company: {company_name}
Careers page: {careers_url}

Here are all the links found on the page:
{all_links}

Instructions:
1. Examine each URL carefully
2. Identify URLs that lead to INDIVIDUAL job postings (not job listing pages, search pages, or filters)
3. Common patterns for job posting URLs:
   - Contains "job", "position", "opening", "vacancy", "role" followed by ID or slug
   - Contains job-specific identifiers like "/details/", "/view/", specific job codes
   - Points to a specific role page (not a search/filter/category page)
4. Exclude:
   - Main careers/jobs listing pages
   - Search/filter pages
   - Category/department pages
   - Navigation links (about, contact, apply tips, etc.)
   - External job boards (LinkedIn, Indeed, etc.) unless no direct links exist
   - Social media, blog posts, news articles
   - Duplicate URLs (keep only unique ones)

Return ONLY a JSON array of the job posting URLs, nothing else. Example:
["https://company.com/jobs/123", "https://company.com/jobs/456"]

If no job posting URLs are found, return an empty array: []
"""


class GeminiClient:
    """Gemini LLM client for filtering job URLs."""

    def __init__(self, model: str = "gemini-2.0-flash-exp", api_key: str | None = None) -> None:
        self.model_name = model
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is not set.")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model)

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        response = self.model.generate_content(
            prompt,
            generation_config={"temperature": temperature},
        )
        return (response.text or "").strip()


def _strip_code_fence(text: str) -> str:
    """Remove markdown code fences from LLM response."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


async def extract_links_from_page(url: str, timeout: int = 60000) -> List[str]:
    """Extract all links from a page using Playwright.
    
    Args:
        url: The careers page URL to scrape
        timeout: Timeout in milliseconds
        
    Returns:
        List of all absolute URLs found on the page
    """
    logger.info(f"Extracting links from {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, timeout=timeout, wait_until="networkidle")
            
            # Wait a bit for any dynamic content to load
            await page.wait_for_timeout(3000)
            
            # Extract all links
            links = await page.evaluate("""
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href]'));
                    return anchors
                        .map(a => a.href)
                        .filter(href => href && href.startsWith('http'));
                }
            """)
            
            # Remove duplicates while preserving order
            unique_links = []
            seen = set()
            for link in links:
                if link not in seen:
                    seen.add(link)
                    unique_links.append(link)
            
            logger.info(f"Extracted {len(unique_links)} unique links from {url}")
            return unique_links
            
        except PlaywrightTimeoutError:
            logger.error(f"Timeout while loading {url}")
            raise
        except Exception as exc:
            logger.error(f"Error extracting links from {url}: {exc}")
            raise
        finally:
            await browser.close()


async def search_google_with_playwright(query: str, max_results: int = 10) -> List[dict]:
    """Search Google using Playwright to scrape search results.
    
    Args:
        query: Search query
        max_results: Maximum number of results to return
        
    Returns:
        List of search result dicts with url, title, snippet
    """
    logger.info(f"Searching Google with Playwright for: {query}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            # Create context with realistic user agent
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US"
            )
            page = await context.new_page()
            
            # Go to Google
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            
            # Wait for search results to load
            await page.wait_for_timeout(2000)
            
            # Take a screenshot for debugging (optional)
            # await page.screenshot(path=f"/tmp/google_search_{query[:20]}.png")
            
            # Get page HTML for debugging
            html = await page.content()
            if "detected unusual traffic" in html.lower() or "captcha" in html.lower():
                logger.warning("Google detected bot traffic or showing CAPTCHA")
            
            # Extract search results
            results = await page.evaluate("""
                () => {
                    const items = [];
                    // Try multiple selectors for different Google layouts
                    const searchResults = document.querySelectorAll('div.g, div[data-sokoban-container], div.Gx5Zad');
                    
                    for (const result of searchResults) {
                        // Find the link
                        const link = result.querySelector('a[href^="http"]');
                        if (!link) continue;
                        
                        const url = link.href;
                        if (!url || url.includes('google.com')) continue;
                        
                        // Find title (h3)
                        const titleElem = result.querySelector('h3');
                        const title = titleElem ? titleElem.textContent : '';
                        
                        // Find snippet/description
                        const snippetElem = result.querySelector('div[data-snf], div[style*="line-clamp"], .VwiC3b, .lyLwlc');
                        const snippet = snippetElem ? snippetElem.textContent : '';
                        
                        if (url && title) {
                            items.push({
                                url: url,
                                title: title,
                                snippet: snippet || '',
                                source: 'google_playwright'
                            });
                        }
                    }
                    
                    return items;
                }
            """)
            
            logger.info(f"Scraped {len(results)} results from Google")
            return results[:max_results]
            
        except Exception as exc:
            logger.error(f"Error searching Google with Playwright: {exc}")
            return []
        finally:
            await context.close()
            await browser.close()


async def scrape_company_website_for_careers(company_name: str) -> List[str]:
    """Scrape the company's main website to find careers page links.
    
    Args:
        company_name: Name of the company
        
    Returns:
        List of potential careers page URLs found on the company website
    """
    logger.info(f"Scraping {company_name} website for careers links")
    
    # Construct likely company website URLs and direct careers page URLs
    company_slug = company_name.lower().replace(" ", "").replace(".", "")
    
    # First, try direct careers page URLs (most specific)
    direct_careers_urls = [
        f"https://careers.{company_slug}.com",
        f"https://jobs.{company_slug}.com",
        f"https://www.{company_slug}.com/careers",
        f"https://{company_slug}.com/careers",
        f"https://explore.jobs.{company_slug}.net/careers",  # Netflix pattern
        f"https://jobs.{company_slug}.net/careers",
        f"https://www.{company_slug}.com/jobs",
        f"https://{company_slug}.com/jobs",
    ]
    
    # Then try main websites to scrape for careers links
    main_websites = [
        f"https://www.{company_slug}.com",
        f"https://{company_slug}.com",
        f"https://www.{company_slug}.io",
        f"https://{company_slug}.io",
        f"https://www.{company_slug}.net",
        f"https://{company_slug}.net",
    ]
    
    potential_sites = direct_careers_urls + main_websites
    
    careers_links = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        try:
            for site_url in potential_sites:
                try:
                    page = await context.new_page()
                    response = await page.goto(site_url, timeout=15000, wait_until="domcontentloaded")
                    
                    if not response or response.status >= 400:
                        logger.debug(f"Site {site_url} returned error status: {response.status if response else 'no response'}")
                        await page.close()
                        continue
                    
                    # Wait a bit more for JavaScript to load
                    await page.wait_for_timeout(2000)
                    
                    # Check if this URL itself is a careers page (direct hit)
                    is_careers_page = any(pattern in site_url.lower() for pattern in ['/careers', '/jobs', 'careers.', 'jobs.'])
                    
                    if is_careers_page:
                        # This is likely a direct careers page - return it immediately
                        logger.info(f"Found direct careers page: {site_url}")
                        careers_links.append(site_url)
                        await page.close()
                        break
                    
                    # Otherwise, extract all links from the page (including text content)
                    links = await page.evaluate("""
                        () => {
                            const anchors = Array.from(document.querySelectorAll('a[href]'));
                            const results = [];
                            
                            for (const anchor of anchors) {
                                const href = anchor.href;
                                const text = (anchor.textContent || '').toLowerCase();
                                
                                // Check if the link or its text mentions careers/jobs
                                if (href && (
                                    href.toLowerCase().includes('career') || 
                                    href.toLowerCase().includes('job') || 
                                    href.toLowerCase().includes('work-with-us') ||
                                    href.toLowerCase().includes('opportunities') ||
                                    text.includes('career') || 
                                    text.includes('job') ||
                                    text.includes('work with us') ||
                                    text.includes('join')
                                )) {
                                    results.push(href);
                                }
                            }
                            
                            return results;
                        }
                    """)
                    
                    if links:
                        logger.info(f"Found {len(links)} potential careers links on {site_url}")
                        careers_links.extend(links)
                        await page.close()
                        break  # Found the website, stop trying other URLs
                    else:
                        logger.debug(f"No careers links found on {site_url}, trying next...")
                    
                    await page.close()
                    
                except Exception as exc:
                    logger.debug(f"Could not access {site_url}: {exc}")
                    continue
                    
        finally:
            await context.close()
            await browser.close()
    
    # Deduplicate and return
    unique_links = list(set(careers_links))
    logger.info(f"Found {len(unique_links)} unique careers links for {company_name}")
    return unique_links


async def search_for_careers_page(company_name: str, llm: GeminiClient) -> str | None:
    """Search for a company's careers page using multiple strategies.
    
    Strategy order:
    1. Scrape company website directly for careers links
    2. Try Playwright-based Google search
    3. Fallback to API-based searches (Google, DuckDuckGo)
    
    Args:
        company_name: Name of the company
        llm: LLM client for selecting best URL
        
    Returns:
        Careers page URL or None if not found
    """
    logger.info(f"Searching for careers page for {company_name}")
    
    search_results = []
    
    # Strategy 1: Scrape company website directly for careers links
    try:
        careers_links = await scrape_company_website_for_careers(company_name)
        if careers_links:
            # Convert to search result format
            search_results = [
                {
                    "url": url,
                    "title": f"{company_name} Careers",
                    "snippet": f"Career opportunities at {company_name}",
                    "source": "company_website"
                }
                for url in careers_links[:10]  # Limit to 10
            ]
            logger.info(f"Found {len(search_results)} careers links from company website")
    except Exception as exc:
        logger.warning(f"Could not scrape company website for {company_name}: {exc}")
    
    # Strategy 2: Try Playwright-based Google search (if website scraping found nothing)
    if not search_results:
        search_query = f"{company_name} careers jobs"
        try:
            search_results = await search_google_with_playwright(search_query, max_results=10)
            if search_results:
                logger.info(f"Found {len(search_results)} results from Google (Playwright) for {company_name}")
        except Exception as exc:
            logger.warning(f"Playwright Google search failed for {company_name}: {exc}")
    
    # Strategy 3: Fallback to API-based searches
    if not search_results:
        search_query = f"{company_name} careers jobs"
        try:
            logger.info(f"Trying API-based Google search for {company_name}")
            search_results = google_search(search_query, max_results=10, debug=False)
            if search_results:
                logger.info(f"Found {len(search_results)} results from Google API for {company_name}")
        except Exception as exc:
            logger.warning(f"Google API search failed for {company_name}: {exc}")
    
    if not search_results:
        try:
            logger.info(f"Trying DuckDuckGo search for {company_name}")
            search_results = duckduckgo_search(search_query, max_results=10, debug=False)
            if search_results:
                logger.info(f"Found {len(search_results)} results from DuckDuckGo for {company_name}")
        except Exception as exc:
            logger.warning(f"DuckDuckGo search failed for {company_name}: {exc}")
    
    if not search_results:
        logger.error(f"All search strategies failed for {company_name}")
        return None
    
    # Use LLM to select the best careers page
    try:
        selection = choose_careers_page(search_results, llm)
        chosen_url = selection.get("chosen_url")
        confidence = selection.get("confidence", "unknown")
        
        if chosen_url:
            logger.info(f"Selected careers page for {company_name}: {chosen_url} (confidence: {confidence})")
            return chosen_url
        else:
            logger.error(f"LLM did not return a careers URL for {company_name}")
            return None
            
    except Exception as exc:
        logger.error(f"Error selecting careers page for {company_name}: {exc}")
        return None


def filter_job_urls_with_llm(
    company_name: str,
    careers_url: str,
    all_links: List[str],
    llm: GeminiClient
) -> List[str]:
    """Use LLM to filter actual job posting URLs from all links.
    
    Args:
        company_name: Name of the company
        careers_url: The careers page URL
        all_links: All links extracted from the page
        llm: LLM client for filtering
        
    Returns:
        Filtered list of job posting URLs
    """
    if not all_links:
        return []
    
    mock_urls = get_mock_response("job_url_extractor", metadata={"company": company_name})
    if mock_urls:
        logger.info("Using mock job URLs for %s", company_name)
        if isinstance(mock_urls, str):
            return [mock_urls]
        if isinstance(mock_urls, list):
            return [str(url) for url in mock_urls]
        logger.warning(
            "Unexpected mock job URL payload for %s (type=%s)",
            company_name,
            type(mock_urls).__name__,
        )
        return []

    logger.info(f"Filtering {len(all_links)} links for {company_name} using LLM")
    
    # Format links as JSON for the prompt
    links_json = json.dumps(all_links, indent=2)
    
    prompt = FILTER_PROMPT.format(
        company_name=company_name,
        careers_url=careers_url,
        all_links=links_json
    )
    
    try:
        response = llm.complete(prompt, temperature=0.0)
        cleaned = _strip_code_fence(response)
        job_urls = json.loads(cleaned)
        
        if not isinstance(job_urls, list):
            logger.error(f"LLM returned non-list response: {cleaned}")
            return []
        
        logger.info(f"LLM identified {len(job_urls)} job posting URLs for {company_name}")
        return job_urls
        
    except json.JSONDecodeError as exc:
        logger.error(f"LLM returned invalid JSON for {company_name}: {exc}")
        return []
    except Exception as exc:
        logger.error(f"Error filtering URLs with LLM for {company_name}: {exc}")
        return []


async def extract_job_urls_for_company(
    company: CompanyInfo,
    llm: GeminiClient,
    timeout: int = 60000
) -> ExtractionResult:
    """Extract job posting URLs for a single company.
    
    Args:
        company: Company information
        llm: LLM client for filtering
        timeout: Timeout in milliseconds
        
    Returns:
        Extraction result with job URLs or error
    """
    logger.info(f"Processing {company.name}")
    
    # If no careers URL provided, search for it
    careers_url = company.careers_url
    if not careers_url:
        logger.info(f"No careers URL provided for {company.name}, searching...")
        careers_url = await search_for_careers_page(company.name, llm)
        
        if not careers_url:
            error_msg = f"Could not find careers page for {company.name}"
            logger.error(error_msg)
            return ExtractionResult(
                company=company.name,
                careers_url="",
                job_urls=[],
                status="no_careers_page",
                error=error_msg
            )
    
    try:
        # Extract all links from the careers page
        all_links = await extract_links_from_page(careers_url, timeout=timeout)
        
        if not all_links:
            logger.warning(f"No links found on {careers_url}")
            return ExtractionResult(
                company=company.name,
                careers_url=careers_url,
                job_urls=[],
                status="no_links",
                error="No links found on the page"
            )
        
        # Filter for job posting URLs using LLM
        job_urls = filter_job_urls_with_llm(
            company.name,
            careers_url,
            all_links,
            llm
        )
        
        if not job_urls:
            logger.warning(f"No job URLs identified for {company.name}")
            return ExtractionResult(
                company=company.name,
                careers_url=careers_url,
                job_urls=[],
                status="no_jobs",
                error="No job posting URLs identified"
            )
        
        logger.info(f"Successfully extracted {len(job_urls)} job URLs for {company.name}")
        return ExtractionResult(
            company=company.name,
            careers_url=careers_url,
            job_urls=job_urls,
            status="success"
        )
        
    except PlaywrightTimeoutError:
        error_msg = f"Timeout loading page: {careers_url}"
        logger.error(error_msg)
        return ExtractionResult(
            company=company.name,
            careers_url=careers_url,
            job_urls=[],
            status="timeout",
            error=error_msg
        )
    except Exception as exc:
        error_msg = f"Error processing {company.name}: {exc}"
        logger.exception(error_msg)
        return ExtractionResult(
            company=company.name,
            careers_url=careers_url,
            job_urls=[],
            status="error",
            error=str(exc)
        )


def read_companies_csv(csv_path: Path) -> List[CompanyInfo]:
    """Read companies and their careers URLs from CSV.
    
    Args:
        csv_path: Path to CSV file with Name,url format (with or without headers)
        
    Returns:
        List of CompanyInfo objects
    """
    companies = []
    
    with csv_path.open(newline="", encoding="utf-8") as handle:
        # Try to detect if file has headers
        first_line = handle.readline().strip()
        handle.seek(0)
        
        # If first line looks like headers (contains 'name' or 'url' case-insensitive), use DictReader
        if first_line.lower().startswith(('name,', 'company,')):
            reader = csv.DictReader(handle)
            for row in reader:
                name = row.get("Name") or row.get("name") or row.get("Company") or row.get("company")
                url = row.get("url") or row.get("URL") or row.get("Url")
                
                if name:
                    name = name.strip()
                    url = url.strip() if url else None
                    companies.append(CompanyInfo(name=name, careers_url=url))
        else:
            # No headers, assume first column is name, second is URL
            reader = csv.reader(handle)
            for row in reader:
                if len(row) >= 2:
                    name = row[0].strip()
                    url = row[1].strip() if row[1].strip() else None
                    if name:
                        companies.append(CompanyInfo(name=name, careers_url=url))
    
    return companies


def append_to_urls_csv(output_csv: Path, results: List[ExtractionResult]) -> int:
    """Append job URLs to the output CSV.
    
    Args:
        output_csv: Path to output CSV file
        results: List of extraction results
        
    Returns:
        Number of URLs written
    """
    # Collect existing URLs to avoid duplicates
    existing_urls: Set[str] = set()
    if output_csv.exists():
        with output_csv.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if "url" in (reader.fieldnames or []):
                for row in reader:
                    url = row.get("url", "").strip()
                    if url:
                        existing_urls.add(url)
        logger.info(f"Found {len(existing_urls)} existing URLs in {output_csv}")
    
    # Collect new URLs
    new_urls = []
    for result in results:
        if result.status == "success":
            for url in result.job_urls:
                if url not in existing_urls:
                    new_urls.append(url)
                    existing_urls.add(url)
    
    if not new_urls:
        logger.warning("No new URLs to append")
        return 0
    
    # Append new URLs
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    file_exists = output_csv.exists()
    
    with output_csv.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["url"])
        
        # Write header if file is new or empty
        if not file_exists or output_csv.stat().st_size == 0:
            writer.writeheader()
        
        for url in new_urls:
            writer.writerow({"url": url})
    
    logger.info(f"Appended {len(new_urls)} new URLs to {output_csv}")
    return len(new_urls)


async def extract_all_job_urls(
    companies_csv: Path,
    output_csv: Path,
    *,
    model: str = "gemini-2.0-flash-exp",
    timeout: int = 60000,
    max_companies: int | None = None
) -> List[ExtractionResult]:
    """Extract job URLs from all companies and save to CSV.
    
    Args:
        companies_csv: Input CSV with company names and careers URLs
        output_csv: Output CSV for job URLs
        model: Gemini model to use for filtering
        timeout: Timeout in milliseconds for page loading
        max_companies: Maximum number of companies to process (for testing)
        
    Returns:
        List of extraction results
    """
    # Read companies
    companies = read_companies_csv(companies_csv)
    if max_companies is not None:
        companies = companies[:max_companies]
    
    logger.info(f"Processing {len(companies)} companies")
    
    # Initialize LLM client
    llm = GeminiClient(model=model)
    
    # Process each company
    results = []
    for idx, company in enumerate(companies, start=1):
        logger.info(f"[{idx}/{len(companies)}] Processing {company.name}")
        result = await extract_job_urls_for_company(company, llm, timeout=timeout)
        results.append(result)
        
        # Small delay between companies to avoid rate limiting
        if idx < len(companies):
            await asyncio.sleep(2)
    
    # Append URLs to output CSV
    total_urls = append_to_urls_csv(output_csv, results)
    
    # Print summary
    logger.info("=" * 80)
    logger.info("EXTRACTION SUMMARY")
    logger.info("=" * 80)
    
    status_counts = {}
    total_jobs = 0
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
        total_jobs += len(result.job_urls)
    
    logger.info(f"Total companies processed: {len(companies)}")
    logger.info(f"Total job URLs extracted: {total_jobs}")
    logger.info(f"New URLs appended to CSV: {total_urls}")
    logger.info("\nStatus breakdown:")
    for status, count in sorted(status_counts.items()):
        logger.info(f"  {status}: {count}")
    
    # Print details for each company
    logger.info("\nPer-company results:")
    for result in results:
        logger.info(f"  {result.company}: {len(result.job_urls)} URLs ({result.status})")
        if result.error:
            logger.info(f"    Error: {result.error}")
    
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract individual job posting URLs from company careers pages"
    )
    parser.add_argument(
        "companies_csv",
        type=Path,
        help="Input CSV with 'Name' and 'url' columns"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/job_urls/sample_urls.csv"),
        help="Output CSV for job URLs (default: data/job_urls/sample_urls.csv)"
    )
    parser.add_argument(
        "--model",
        default="gemini-2.0-flash-exp",
        help="Gemini model for URL filtering (default: gemini-2.0-flash-exp)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60000,
        help="Page load timeout in milliseconds (default: 60000)"
    )
    parser.add_argument(
        "--max-companies",
        type=int,
        help="Maximum number of companies to process (for testing)"
    )
    
    args = parser.parse_args()
    
    try:
        results = asyncio.run(
            extract_all_job_urls(
                args.companies_csv,
                args.output,
                model=args.model,
                timeout=args.timeout,
                max_companies=args.max_companies
            )
        )
        
        # Return 0 if at least some URLs were extracted
        success_count = sum(1 for r in results if r.status == "success")
        return 0 if success_count > 0 else 1
        
    except Exception as exc:
        logger.exception("Job URL extraction failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
