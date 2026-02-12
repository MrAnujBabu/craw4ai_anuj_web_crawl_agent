"""Test if matching UA to actual platform fixes Akamai detection."""
import asyncio
import os
import shutil
import uuid
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.async_configs import ProxyConfig


async def test_with_ua(label, user_agent):
    print(f"\n{'='*60}")
    print(f"Test: {label}")
    print(f"{'='*60}")

    profile_dir = os.path.expanduser(f"~/.crawl4ai/test_{uuid.uuid4().hex[:8]}")
    os.makedirs(profile_dir, exist_ok=True)

    browser_config = BrowserConfig(
        headless=True,
        enable_stealth=True,
        use_persistent_context=True,
        user_data_dir=profile_dir,
        viewport_width=1920,
        viewport_height=1080,
        user_agent=user_agent,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        },
        proxy_config=ProxyConfig(
            server="https://network.joinmassive.com:65535",
            username="mpuQHs4sWZ-country-US",
            password="D0yWxVQo8wQ05RWqz1Bn",
        ),
    )

    run_config = CrawlerRunConfig(
        magic=True,
        simulate_user=True,
        override_navigator=True,
        page_timeout=120000,
        wait_until="load",
        delay_before_return_html=10.0,
    )

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                "https://www.chanel.com/us/fashion/handbags/c/1x1x1/",
                config=run_config,
            )
            print(f"  Status: {result.status_code}")
            print(f"  HTML bytes: {len(result.html)}")
            blocked = "access denied" in result.html.lower()
            print(f"  Blocked: {blocked}")
            if not blocked and len(result.html) > 1000:
                print(f"  SUCCESS! Got real content")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


async def main():
    # Mac UA on Linux = platform mismatch
    await test_with_ua(
        "Mac UA (mismatched platform)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    )

    await asyncio.sleep(3)

    # Linux UA = matches actual navigator.platform
    await test_with_ua(
        "Linux UA (matching platform)",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    )


asyncio.run(main())
