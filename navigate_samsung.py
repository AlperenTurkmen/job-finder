"""Navigate to Samsung careers page using BrowserMCP."""
import os
from dotenv import load_dotenv
from browser_client import fetch_page_markdown
from logging_utils import get_logger

# Load environment variables from config/.env
load_dotenv("config/.env")

logger = get_logger(__name__)

if __name__ == "__main__":
    url = "https://sec.wd3.myworkdayjobs.com/en-US/Samsung_Careers/details/Internship-Display_R100686?q=netherlands"
    
    logger.info(f"Navigating to: {url}")
    
    try:
        markdown = fetch_page_markdown(url, timeout=30)
        
        logger.info(f"Successfully fetched page content ({len(markdown)} characters)")
        print("\n" + "="*80)
        print("PAGE CONTENT")
        print("="*80 + "\n")
        print(markdown)
        
        # Optionally save to file
        output_file = "samsung_internship_page.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown)
        logger.info(f"Saved content to {output_file}")
        
    except Exception as e:
        logger.error(f"Error fetching page: {e}", exc_info=True)
        raise
