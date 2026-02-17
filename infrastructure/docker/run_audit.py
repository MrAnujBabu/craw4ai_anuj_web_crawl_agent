"""
Docker container entrypoint for SEO audit jobs.

Receives job parameters via environment variables, runs crawl4ai + SEO audit,
then POSTs results back to the Cloudflare Worker gateway.

Environment variables:
    JOB_ID          - UUID of the crawl job
    START_URL       - URL to start crawling
    CALLBACK_URL    - Worker endpoint to POST results to
    API_KEY         - Bearer token for the Worker
    MAX_PAGES       - Max pages to crawl (default: 50)
    MAX_DEPTH       - Max crawl depth (default: 3)
"""

import os
import sys
import json
import asyncio
import logging
import httpx

# Ensure crawl4ai is importable
sys.path.insert(0, "/app")

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.seo_audit import SEOAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seo-audit-runner")


async def run():
    job_id = os.environ["JOB_ID"]
    start_url = os.environ["START_URL"]
    callback_url = os.environ["CALLBACK_URL"]
    api_key = os.environ["API_KEY"]
    max_pages = int(os.environ.get("MAX_PAGES", "50"))
    max_depth = int(os.environ.get("MAX_DEPTH", "3"))

    logger.info(f"Starting audit job {job_id} for {start_url} (max_pages={max_pages}, max_depth={max_depth})")

    analyzer = SEOAnalyzer()
    crawl_results = []

    try:
        crawl_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            deep_crawl_strategy=BFSDeepCrawlStrategy(
                max_depth=max_depth,
                max_pages=max_pages,
            ),
        )

        async with AsyncWebCrawler() as crawler:
            results = await crawler.arun(url=start_url, config=crawl_config)

            # arun with deep crawl returns a list
            if isinstance(results, list):
                crawl_results = results
            else:
                crawl_results = [results]

        logger.info(f"Crawled {len(crawl_results)} pages")

        # Run SEO audit
        site_result = analyzer.analyze_site(crawl_results)
        logger.info(f"Audit complete. Score: {site_result.summary.score}/100")

        # Prepare payload for the Worker
        pages_payload = []
        snapshots_payload = []

        for url, page_audit in site_result.page_details.items():
            pages_payload.append({
                "url": page_audit.url,
                "status_code": page_audit.status_code,
                "title": page_audit.title.value,
                "title_length": page_audit.title.length,
                "title_status": page_audit.title.status.value,
                "meta_desc": page_audit.meta_description.value,
                "meta_desc_length": page_audit.meta_description.length,
                "meta_desc_status": page_audit.meta_description.status.value,
                "h1_count": page_audit.headings.h1_count,
                "has_canonical": page_audit.canonical.value is not None,
                "is_indexable": page_audit.robots.is_indexable,
                "has_json_ld": page_audit.structured_data.has_json_ld,
                "has_viewport": page_audit.viewport.status.value == "pass",
                "has_og_tags": page_audit.open_graph.status.value != "fail",
                "word_count": page_audit.content.word_count,
                "images_total": page_audit.images.total,
                "images_no_alt": page_audit.images.missing_alt,
                "internal_links": page_audit.links.internal_count,
                "external_links": page_audit.links.external_count,
                "mixed_content": page_audit.mixed_content.has_mixed_content,
                "audit_json": page_audit.model_dump_json(),
            })

        # Get HTML snapshots from crawl results
        for cr in crawl_results:
            if cr.success and cr.html:
                snapshots_payload.append({
                    "url": cr.url,
                    "html": cr.html[:500_000],  # Cap at 500KB per page
                })

        issues_payload = []
        for issue in site_result.critical + site_result.warnings + site_result.info:
            issues_payload.append({
                "issue_type": issue.issue_type,
                "severity": issue.severity.value,
                "description": issue.description,
                "fix": issue.fix,
                "affected_count": len(issue.affected_pages),
                "affected_urls": issue.affected_pages[:50],  # Cap URLs
            })

        # Strip page_details from audit_json to keep it small
        summary_dict = site_result.summary.model_dump()
        summary_payload = {
            "pages_audited": summary_dict["pages_audited"],
            "score": summary_dict["score"],
            "issues_critical": summary_dict["issues_critical"],
            "issues_warning": summary_dict["issues_warning"],
            "issues_info": summary_dict["issues_info"],
            "audit_json": json.dumps({
                "summary": summary_dict,
                "critical_count": len(site_result.critical),
                "warning_count": len(site_result.warnings),
                "info_count": len(site_result.info),
            }),
        }

        payload = {
            "status": "completed",
            "pages": pages_payload,
            "issues": issues_payload,
            "summary": summary_payload,
            "snapshots": snapshots_payload,
        }

        # POST results back to Worker
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                callback_url,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()

        logger.info(f"Results posted to {callback_url}. Done.")

    except Exception as e:
        logger.error(f"Audit failed: {e}", exc_info=True)
        # Report failure to Worker
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                await client.post(
                    callback_url,
                    json={"status": "failed", "error": str(e)},
                    headers={"Authorization": f"Bearer {api_key}"},
                )
        except Exception:
            logger.error("Failed to report error to callback URL")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
