import asyncio
import os
import shutil
import uuid
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, UndetectedAdapter
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy


async def attempt(label, browser_config, run_config, crawler_strategy=None):
    print(f"\n{'='*60}")
    print(f"Attempt: {label}")
    print(f"{'='*60}")

    url = "https://www.chanel.com/us/fashion/handbags/c/1x1x1/"

    kwargs = {"config": browser_config}
    if crawler_strategy:
        kwargs["crawler_strategy"] = crawler_strategy

    try:
        async with AsyncWebCrawler(**kwargs) as crawler:
            result = await crawler.arun(url, config=run_config)
            print(f"Status: {result.status_code}")
            print(f"Success: {result.success}")
            print(f"HTML: {len(result.html):,} bytes")
            if result.markdown:
                print(f"Markdown: {len(result.markdown.raw_markdown):,} chars")
            if result.error_message:
                print(f"Error: {result.error_message}")
            # Check for anti-bot indicators
            html_lower = result.html.lower()
            for indicator in ["access denied", "403", "blocked", "captcha", "challenge"]:
                if indicator in html_lower:
                    print(f"  Anti-bot indicator found: '{indicator}'")
            return result
    except Exception as e:
        print(f"Exception: {e}")
        return None


async def main():
    mac_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    # ---- Attempt 1: Mac UA + stealth (user's original approach) ----
    profile1 = os.path.expanduser(f"~/.crawl4ai/chanel_{uuid.uuid4().hex[:8]}")
    os.makedirs(profile1, exist_ok=True)
    try:
        bc1 = BrowserConfig(
            headless=True,
            enable_stealth=True,
            use_persistent_context=True,
            user_data_dir=profile1,
            viewport_width=1920,
            viewport_height=1080,
            user_agent=mac_ua,
            headers=headers,
        )
        rc1 = CrawlerRunConfig(
            magic=True,
            simulate_user=True,
            override_navigator=True,
            page_timeout=120000,
            wait_until="load",
            delay_before_return_html=10.0,
        )
        await attempt("Mac UA + Stealth + Magic (user's script)", bc1, rc1)
    finally:
        shutil.rmtree(profile1, ignore_errors=True)

    await asyncio.sleep(3)

    # ---- Attempt 2: Undetected adapter (patchright) ----
    profile2 = os.path.expanduser(f"~/.crawl4ai/chanel_{uuid.uuid4().hex[:8]}")
    os.makedirs(profile2, exist_ok=True)
    try:
        bc2 = BrowserConfig(
            headless=True,
            use_persistent_context=True,
            user_data_dir=profile2,
            viewport_width=1920,
            viewport_height=1080,
            user_agent=mac_ua,
            headers=headers,
        )
        rc2 = CrawlerRunConfig(
            simulate_user=True,
            override_navigator=True,
            page_timeout=120000,
            wait_until="load",
            delay_before_return_html=15.0,
        )
        adapter = UndetectedAdapter()
        strategy = AsyncPlaywrightCrawlerStrategy(
            browser_config=bc2,
            browser_adapter=adapter,
        )
        await attempt("Undetected Adapter (patchright)", bc2, rc2, crawler_strategy=strategy)
    finally:
        shutil.rmtree(profile2, ignore_errors=True)

    await asyncio.sleep(3)

    # ---- Attempt 3: Longer delay + networkidle ----
    profile3 = os.path.expanduser(f"~/.crawl4ai/chanel_{uuid.uuid4().hex[:8]}")
    os.makedirs(profile3, exist_ok=True)
    try:
        bc3 = BrowserConfig(
            headless=True,
            enable_stealth=True,
            use_persistent_context=True,
            user_data_dir=profile3,
            viewport_width=1920,
            viewport_height=1080,
            user_agent=mac_ua,
            headers=headers,
        )
        rc3 = CrawlerRunConfig(
            magic=True,
            simulate_user=True,
            override_navigator=True,
            page_timeout=120000,
            wait_until="networkidle",
            delay_before_return_html=20.0,
            js_code="""
            // Simulate human-like scrolling
            await new Promise(r => setTimeout(r, 2000));
            window.scrollTo({top: 300, behavior: 'smooth'});
            await new Promise(r => setTimeout(r, 1500));
            window.scrollTo({top: 600, behavior: 'smooth'});
            await new Promise(r => setTimeout(r, 1000));
            """,
        )
        await attempt("Stealth + networkidle + scroll + 20s delay", bc3, rc3)
    finally:
        shutil.rmtree(profile3, ignore_errors=True)


asyncio.run(main())
