import asyncio
import os
import json
import requests
from crawl4ai import AsyncWebCrawler

async def main():
    # 1. Get inputs from environment variables (passed from GitHub Action)
    target_url = os.getenv('TARGET_URL')
    callback_url = os.getenv('CALLBACK_URL')
    
    if not target_url or not callback_url:
        print("Error: TARGET_URL and CALLBACK_URL are required.")
        return

    print(f"Starting crawl for: {target_url}")

    # 2. Run Crawl4AI
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=target_url)
            
            # Prepare the payload
            payload = {
                "url": result.url,
                "markdown": result.markdown,
                "html": result.html,  # Optional: remove if payload is too large
                "success": True
            }
    except Exception as e:
        payload = {
            "url": target_url,
            "error": str(e),
            "success": False
        }

    # 3. Send data back to n8n Webhook
    print(f"Sending results to: {callback_url}")
    try:
        response = requests.post(callback_url, json=payload)
        print(f"Webhook response: {response.status_code}")
    except Exception as e:
        print(f"Failed to send webhook: {e}")

if __name__ == "__main__":
    asyncio.run(main())
