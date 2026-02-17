"""
Test script to examine Netflix careers page structure.
Helps debug why job URLs aren't being extracted.
"""

import asyncio
from playwright.async_api import async_playwright
import json


async def test_netflix_structure():
    """Examine the Netflix careers page structure."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Go to Netflix careers search
        url = "https://explore.jobs.netflix.net/careers?query=*&location=London%2C%20United%20Kingdom"
        print(f"Loading: {url}")
        await page.goto(url, wait_until="networkidle")
        
        # Wait for job cards
        try:
            await page.wait_for_selector(".position-card", timeout=15000)
            print("✅ Found position cards")
        except Exception as e:
            print(f"❌ No position cards found: {e}")
            await browser.close()
            return
        
        # Get first job card
        card = await page.query_selector(".position-card")
        
        if card:
            print("\n" + "=" * 60)
            print("ANALYZING FIRST JOB CARD")
            print("=" * 60)
            
            # Get the card's HTML
            card_html = await card.inner_html()
            print("\n--- Card HTML (first 500 chars) ---")
            print(card_html[:500])
            
            # Check for links
            links = await card.query_selector_all("a")
            print(f"\n--- Found {len(links)} links in card ---")
            for i, link in enumerate(links[:3]):  # First 3 links
                href = await link.get_attribute("href")
                text = await link.inner_text()
                print(f"{i+1}. href: {href}")
                print(f"   text: {text[:50] if text else '(no text)'}...")
            
            # Check card attributes
            print("\n--- Card Attributes ---")
            card_id = await card.get_attribute("id")
            card_class = await card.get_attribute("class")
            data_attrs = await page.evaluate("""(card) => {
                const attrs = {};
                for (let attr of card.attributes) {
                    if (attr.name.startsWith('data-')) {
                        attrs[attr.name] = attr.value;
                    }
                }
                return attrs;
            }""", card)
            
            print(f"ID: {card_id}")
            print(f"Class: {card_class}")
            print(f"Data attributes: {json.dumps(data_attrs, indent=2)}")
            
            # Check if card itself is clickable
            onclick = await card.get_attribute("onclick")
            print(f"onclick: {onclick}")
            
            # Try to find job ID in various places
            print("\n--- Looking for Job ID ---")
            
            # Check URL in title link
            title_link = await card.query_selector("a.position-title")
            if title_link:
                href = await title_link.get_attribute("href")
                print(f"Title link href: {href}")
            
            # Check for hidden inputs or data attributes with job ID
            inputs = await card.query_selector_all("input[type='hidden']")
            print(f"Hidden inputs: {len(inputs)}")
            for inp in inputs:
                name = await inp.get_attribute("name")
                value = await inp.get_attribute("value")
                print(f"  {name} = {value}")
        
        # Also check page source for embedded JSON
        print("\n" + "=" * 60)
        print("CHECKING FOR EMBEDDED JSON")
        print("=" * 60)
        
        html_content = await page.content()
        
        # Look for window.__INITIAL_STATE__ or similar
        if "window.__INITIAL_STATE__" in html_content:
            print("✅ Found window.__INITIAL_STATE__")
        if "window.CAREERS_DATA" in html_content:
            print("✅ Found window.CAREERS_DATA")
        if '"id":' in html_content and '"name":' in html_content:
            print("✅ Found JSON with id and name fields")
            # Find first occurrence
            import re
            match = re.search(r'\{"id":\s*\d+[^}]{0,200}', html_content)
            if match:
                print(f"Sample: {match.group()}")
        
        # Wait so we can inspect in browser
        print("\n\nBrowser will stay open for 30 seconds for manual inspection...")
        await asyncio.sleep(30)
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_netflix_structure())
