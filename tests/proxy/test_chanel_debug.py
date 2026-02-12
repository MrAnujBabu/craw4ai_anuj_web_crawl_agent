import asyncio
import os
import shutil
import uuid
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.async_configs import ProxyConfig


async def main():
    profile_dir = os.path.expanduser(f"~/.crawl4ai/chanel_{uuid.uuid4().hex[:8]}")
    os.makedirs(profile_dir, exist_ok=True)

    browser_config = BrowserConfig(
        headless=True,
        enable_stealth=True,
        use_persistent_context=True,
        user_data_dir=profile_dir,
        viewport_width=1920,
        viewport_height=1080,
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
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
        wait_until="networkidle",
        delay_before_return_html=15.0,
    )

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                "https://www.chanel.com/us/fashion/handbags/c/1x1x1/",
                config=run_config,
            )
            print(f"Status: {result.status_code}")
            print(f"HTML bytes: {len(result.html)}")
            print(f"\n=== FULL HTML ===\n{result.html}")
            print(f"\n=== RESPONSE HEADERS ===")
            if result.response_headers:
                for k, v in sorted(result.response_headers.items()):
                    print(f"  {k}: {v}")
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


asyncio.run(main())
