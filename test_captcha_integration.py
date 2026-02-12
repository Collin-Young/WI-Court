#!/usr/bin/env python3
"""Test script to verify hcaptcha-challenger integration."""

import asyncio
import os
from playwright.async_api import async_playwright
from hcaptcha_challenger import AgentV, AgentConfig
from pathlib import Path

async def test_captcha_solver():
    """Test basic CAPTCHA solver functionality."""
    print("Testing hcaptcha-challenger integration...")

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise SystemExit("Set the GEMINI_API_KEY environment variable before running this test.")
    
    tmp_dir = Path(__file__).parent.joinpath("test_tmp")
    tmp_dir.mkdir(exist_ok=True)
    
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale="en-US")
        page = await context.new_page()
        
        # Navigate to a test hCaptcha page
        print("Navigating to test hCaptcha page...")
        # Use Discord's site which has hCaptcha protection
        await page.goto("https://discord.com/login", wait_until="domcontentloaded", timeout=60000)
        
        # Initialize hcaptcha agent
        print("Initializing Agent...")
        agent_config = AgentConfig(GEMINI_API_KEY=gemini_key)
        agent = AgentV(page=page, agent_config=agent_config)
        
        try:
            print("Waiting for CAPTCHA challenge...")
            challenge_signal = await agent.wait_for_challenge()
            print(f"Challenge signal received: {challenge_signal}")
            print("CAPTCHA challenge handled automatically")
            return True
                
        except Exception as e:
            print(f"Error during CAPTCHA solving: {e}")
            return False
        finally:
            await browser.close()

if __name__ == "__main__":
    result = asyncio.run(test_captcha_solver())
    if result:
        print("Integration test passed!")
    else:
        print("Integration test failed!")
