"""Navigate to Samsung careers page using Playwright directly."""
import asyncio
from playwright.async_api import async_playwright
from logging_utils import get_logger

logger = get_logger(__name__)

async def navigate_to_url(url: str):
    """Navigate to URL and extract content."""
    logger.info(f"Navigating to: {url}")
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=False)  # Set to True for headless mode
        page = await browser.new_page()
        
        try:
            # Navigate to the URL
            await page.goto(url, wait_until="networkidle")
            
            # Get the page title
            title = await page.title()
            logger.info(f"Page title: {title}")
            
            # Get the main content
            content = await page.content()
            
            # Extract text content
            text_content = await page.inner_text('body')
            
            logger.info(f"Successfully extracted content ({len(text_content)} characters)")
            
            # Save to file
            output_file = "samsung_internship_page.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(f"Title: {title}\n\n")
                f.write(f"URL: {url}\n\n")
                f.write("="*80 + "\n")
                f.write(text_content)
            
            logger.info(f"Saved content to {output_file}")
            
            # Optional: Take a screenshot
            screenshot_file = "samsung_internship_page.png"
            await page.screenshot(path=screenshot_file, full_page=True)
            logger.info(f"Saved screenshot to {screenshot_file}")
            
            return text_content
            
        except Exception as e:
            logger.error(f"Error during navigation: {e}", exc_info=True)
            raise
            
        finally:
            await browser.close()


if __name__ == "__main__":
    url = "https://sec.wd3.myworkdayjobs.com/en-US/Samsung_Careers/details/Internship-Display_R100686?q=netherlands"
    
    # Run the async function
    asyncio.run(navigate_to_url(url))
