"""LLM-based content cleaner to extract job information from scraped pages."""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
import google.generativeai as genai

from utils.logging import get_logger

load_dotenv()

logger = get_logger(__name__)


def clean_job_content(raw_text: str, url: str) -> str:
    """Use Gemini to extract only the job posting content from scraped text.
    
    Args:
        raw_text: Raw text from the scraped page (includes headers, footers, navigation, etc.)
        url: The job posting URL (for context)
    
    Returns:
        Cleaned text containing only the job posting information
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("No GEMINI_API_KEY found, returning raw text without cleaning")
        return raw_text
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"))
    
    prompt = f"""Extract ONLY the job posting information from the following scraped webpage content.

URL: {url}

Remove all navigation menus, headers, footers, cookie notices, social media links, and other non-job-related content.

Keep ONLY:
- Job title
- Location
- Job description
- Responsibilities/duties
- Requirements/qualifications
- Benefits (if mentioned)
- Application instructions (if mentioned)
- Any other job-specific information

Return the cleaned job posting as plain text. Do not add any commentary or explanations.

SCRAPED CONTENT:
{raw_text}

CLEANED JOB POSTING:"""

    try:
        logger.debug("Sending %d characters to Gemini for cleaning", len(raw_text))
        response = model.generate_content(prompt)
        cleaned = response.text.strip()
        logger.info("LLM cleaned content: %d -> %d characters", len(raw_text), len(cleaned))
        return cleaned
    except Exception as exc:
        logger.error("Failed to clean content with LLM: %s", exc)
        logger.warning("Returning raw text")
        return raw_text
