import os
import json
import asyncio
import requests
from crawl4ai import AsyncWebCrawler

async def crawl():
    url = os.environ.get('TARGET_URL')
    resume_url = os.environ.get('RESUME_URL')
    
    print(f"Starting crawl for: {url}")
    
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        
        output = {
            "url": url,
            "markdown": result.markdown,
            "success": result.success
        }
        
        # Send results back to n8n
        if resume_url:
            response = requests.post(resume_url, json=output)
            print(f"Sent to n8n: {response.status_code}")
        
        return output

if __name__ == "__main__":
    asyncio.run(crawl())
