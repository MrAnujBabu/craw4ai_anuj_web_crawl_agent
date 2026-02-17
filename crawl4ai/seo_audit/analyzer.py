"""
SEOAnalyzer — main orchestrator for SEO audits.

Provides both single-page and multi-page (site-wide) audit capabilities.
Designed to work with crawl4ai's CrawlResult objects as input.

Ported from seo-audit-mcp's run-audit.ts orchestration logic, adapted
to crawl4ai's Python architecture.
"""

from typing import Dict, List, Optional
from collections import defaultdict
from urllib.parse import urlparse, urljoin

from ..models import CrawlResult
from .models import (
    PageAuditResult,
    SiteAuditResult,
    SiteAuditSummary,
)
from .checks import audit_page
from .site_checks import run_site_checks


class SEOAnalyzer:
    """
    SEO audit analyzer that processes crawl4ai CrawlResult objects.

    Usage — single page:
        analyzer = SEOAnalyzer()
        result = analyzer.analyze_page(crawl_result)

    Usage — site-wide (from a list of CrawlResult):
        analyzer = SEOAnalyzer()
        site_result = analyzer.analyze_site(crawl_results)
    """

    def analyze_page(self, crawl_result: CrawlResult) -> PageAuditResult:
        """
        Run all SEO checks on a single crawled page.

        Args:
            crawl_result: A CrawlResult from crawl4ai's crawler.

        Returns:
            PageAuditResult with all per-page SEO checks.
        """
        html = crawl_result.html or ""
        return audit_page(
            url=crawl_result.url,
            raw_html=html,
            status_code=crawl_result.status_code,
        )

    def analyze_site(
        self, crawl_results: List[CrawlResult]
    ) -> SiteAuditResult:
        """
        Run full site-wide SEO audit across multiple crawled pages.

        Args:
            crawl_results: List of CrawlResult objects from crawling a site.

        Returns:
            SiteAuditResult with summary, issues, and per-page details.
        """
        page_results: Dict[str, PageAuditResult] = {}
        link_graph: Dict[str, List[str]] = {}

        for result in crawl_results:
            if not result.success:
                continue

            # Run per-page audit
            page_audit = self.analyze_page(result)
            page_results[result.url] = page_audit

            # Build internal link graph from crawl4ai's extracted links
            internal_links = self._extract_internal_links(result)
            link_graph[result.url] = internal_links

        return run_site_checks(page_results, internal_link_graph=link_graph)

    def analyze_html(
        self, url: str, html: str, status_code: Optional[int] = None
    ) -> PageAuditResult:
        """
        Run all SEO checks on raw HTML (without a CrawlResult).

        Useful for standalone analysis or testing.
        """
        return audit_page(url=url, raw_html=html, status_code=status_code)

    def _extract_internal_links(self, result: CrawlResult) -> List[str]:
        """Extract internal link URLs from CrawlResult's links dict."""
        internal_urls = []
        internal_links = result.links.get("internal", [])
        for link in internal_links:
            href = link.get("href", "") if isinstance(link, dict) else ""
            if href:
                internal_urls.append(href)
        return internal_urls
