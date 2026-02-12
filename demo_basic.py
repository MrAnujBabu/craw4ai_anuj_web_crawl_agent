import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai import JsonCssExtractionStrategy
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter


async def example_1_basic_crawl():
    print("\n" + "="*60)
    print("示例 1: 基础爬取")
    print("="*60)
    
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url="https://example.com")
        print(f"成功: {result.success}")
        print(f"标题: {result.metadata.get('title', 'N/A')}")
        print(f"Markdown 长度: {len(result.markdown)} 字符")
        print(f"Markdown 内容预览:\n{result.markdown[:200]}...")


async def example_2_clean_content():
    print("\n" + "="*60)
    print("示例 2: 清理内容（移除导航、页脚等）")
    print("="*60)
    
    config = CrawlerRunConfig(
        excluded_tags=["nav", "footer", "aside"],
        remove_overlay_elements=True,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.48)
        ),
    )
    
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url="https://en.wikipedia.org/wiki/Python", config=config)
        print(f"清理后 Markdown 长度: {len(result.markdown)} 字符")
        print(f"内容预览:\n{result.markdown[:300]}...")


async def example_3_css_extraction():
    print("\n" + "="*60)
    print("示例 3: CSS 选择器提取结构化数据")
    print("="*60)
    
    schema = {
        "name": "News Articles",
        "baseSelector": "article",
        "fields": [
            {"name": "title", "selector": "h2, h3", "type": "text"},
            {"name": "link", "selector": "a", "type": "attribute", "attribute": "href"},
        ]
    }
    
    config = CrawlerRunConfig(
        extraction_strategy=JsonCssExtractionStrategy(schema),
        css_selector="article",
    )
    
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url="https://example.com", config=config)
        print(f"提取成功: {result.success}")
        if result.extracted_content:
            print(f"提取的内容:\n{result.extracted_content[:300]}...")


async def example_4_javascript_execution():
    print("\n" + "="*60)
    print("示例 4: 执行 JavaScript")
    print("="*60)
    
    config = CrawlerRunConfig(
        js_code="document.body.style.backgroundColor = '#f0f0f0';",
        delay_before_return_html=0.5,
    )
    
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url="https://example.com", config=config)
        print(f"JavaScript 执行成功: {result.success}")
        print(f"页面标题: {result.metadata.get('title', 'N/A')}")


async def example_5_screenshot():
    print("\n" + "="*60)
    print("示例 5: 截图")
    print("="*60)
    
    config = CrawlerRunConfig(screenshot=True)
    
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url="https://example.com", config=config)
        print(f"截图成功: {result.success}")
        if result.screenshot:
            print(f"截图数据长度: {len(result.screenshot)} 字节")
            import base64
            with open("example_screenshot.png", "wb") as f:
                f.write(base64.b64decode(result.screenshot))
            print("截图已保存到: example_screenshot.png")


async def example_6_links_analysis():
    print("\n" + "="*60)
    print("示例 6: 链接分析")
    print("="*60)
    
    config = CrawlerRunConfig(
        exclude_external_links=False,
        exclude_social_media_links=False,
    )
    
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url="https://example.com", config=config)
        internal_links = result.links.get("internal", [])
        external_links = result.links.get("external", [])
        
        print(f"内部链接数量: {len(internal_links)}")
        print(f"外部链接数量: {len(external_links)}")
        
        if internal_links:
            print("\n内部链接示例:")
            for link in internal_links[:3]:
                print(f"  - {link.get('href', 'N/A')}")


async def main():
    print("\n" + "🚀 Crawl4AI 基础示例演示 🚀")
    print("="*60)
    
    await example_1_basic_crawl()
    await example_2_clean_content()
    await example_3_css_extraction()
    await example_4_javascript_execution()
    await example_5_screenshot()
    await example_6_links_analysis()
    
    print("\n" + "="*60)
    print("✅ 所有示例运行完成！")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
