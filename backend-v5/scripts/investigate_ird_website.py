#!/usr/bin/env python3
"""
Investigate IRD website structure to understand search capabilities.
"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print("Loading IRD website...")
        await page.goto("https://ird.gov.np/pan-search/", wait_until="networkidle")

        print("Waiting 5 seconds for you to see the page...")
        await asyncio.sleep(5)

        # Get page HTML
        html = await page.content()

        # Save to file
        with open("/app/investigation_output/ird_page_structure.html", "w", encoding="utf-8") as f:
            f.write(html)

        print("HTML saved to /app/investigation_output/ird_page_structure.html")

        # Take screenshot
        await page.screenshot(path="/app/investigation_output/ird_screenshot.png")
        print("Screenshot saved to /app/investigation_output/ird_screenshot.png")

        # Get all input fields
        inputs = await page.query_selector_all("input")
        print(f"\nFound {len(inputs)} input fields:")
        for inp in inputs:
            input_id = await inp.get_attribute("id")
            input_name = await inp.get_attribute("name")
            input_type = await inp.get_attribute("type")
            input_placeholder = await inp.get_attribute("placeholder")
            print(f"  - ID: {input_id}, Name: {input_name}, Type: {input_type}, Placeholder: {input_placeholder}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
