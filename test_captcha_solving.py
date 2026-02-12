"""Test script to verify hcaptcha-challenger integration with a known CAPTCHA site."""

import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright
from hcaptcha_challenger import AgentV, AgentConfig
from hcaptcha_challenger.utils import SiteKey

async def test_captcha_solving():
    """Test CAPTCHA solving on a known protected site."""
    print("Testing hcaptcha-challenger with known CAPTCHA site...")

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise SystemExit("Set the GEMINI_API_KEY environment variable before running this test.")
    
    tmp_dir = Path(__file__).parent.joinpath("tmp_dir")
    tmp_dir.mkdir(exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale="en-US")
        page = await context.new_page()
        
        # Use hCaptcha's test site
        test_url = SiteKey.as_site_link(SiteKey.user_easy)
        print(f"Navigating to {test_url}...")
        await page.goto(test_url, wait_until="domcontentloaded", timeout=60000)
        
        # Initialize hcaptcha agent
        agent_config = AgentConfig(GEMINI_API_KEY=gemini_key)
        agent = AgentV(page=page, agent_config=agent_config)
        
        print("Waiting for CAPTCHA challenge...")
        try:
            # First, click the checkbox to trigger the CAPTCHA
            await agent.robotic_arm.click_checkbox()
            print("Checkbox clicked, waiting for challenge...")
            
            # Then wait for and handle the CAPTCHA challenge
            challenge_signal = await agent.wait_for_challenge()
            print(f"CAPTCHA challenge signal: {challenge_signal}")
            
            # If we get here, CAPTCHA was handled
            print("CAPTCHA solved successfully!")
            return True
            
        except Exception as e:
            print(f"CAPTCHA solving failed: {e}")
            return False
        
        finally:
            await browser.close()

if __name__ == "__main__":
    result = asyncio.run(test_captcha_solving())
    if result:
        print("CAPTCHA solving test passed!")
    else:
        print("CAPTCHA solving test failed!")
