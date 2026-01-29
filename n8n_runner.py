import os
import json
import asyncio
from crawl4ai import AsyncWebCrawler

async def crawl():
    url = os.environ.get('TARGET_URL')
    print(f"Starting crawl for: {url}")
    
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        
        output = {
            "url": url,
            "markdown": result.markdown,
            "success": result.success
        }
        
        # Write to GitHub Actions output
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            # For large content, write to file and output path
            f.write(f"result={json.dumps(output)}\n")
        
        print("Crawl complete!")
        return output

if __name__ == "__main__":
    asyncio.run(crawl())
