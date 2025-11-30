"""CLI entrypoint for the job scraper agent."""
from __future__ import annotations

import argparse
import sys
from typing import NoReturn

from browser_client import BrowserMCPError, BrowserMCPTimeoutError
from job_scraper_agent import URLValidationError, run_job_scraper
from logging_utils import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scrape.py",
        description="Fetch raw job posting text via the BrowserMCP-backed Gemini agent.",
    )
    parser.add_argument("url", help="Absolute URL to the job posting to scrape.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Optional override for the BrowserMCP timeout in seconds.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Disable LLM-based content cleaning (return raw scraped content).",
    )
    return parser.parse_args()


def main() -> NoReturn:
    args = _parse_args()
    try:
        result = run_job_scraper(
            args.url, 
            timeout=args.timeout,
            clean_with_llm=not args.no_clean
        )
    except URLValidationError as exc:
        logger.error("Invalid URL: %s", exc)
        sys.exit(2)
    except BrowserMCPTimeoutError as exc:
        logger.error("BrowserMCP timeout: %s", exc)
        sys.exit(3)
    except BrowserMCPError as exc:
        logger.error("BrowserMCP failure: %s", exc)
        sys.exit(4)
    except Exception as exc:  # pragma: no cover - defensive last resort
        logger.exception("Unexpected error while scraping")
        sys.exit(1)

    print(result)
    sys.exit(0)


if __name__ == "__main__":
    main()
