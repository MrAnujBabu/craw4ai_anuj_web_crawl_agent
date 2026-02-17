"""
crawl4ai.seo_audit — SEO audit layer for crawl4ai.

Ported from RichardDillman/seo-audit-mcp and adapted to work with
crawl4ai's CrawlResult pipeline.

Usage:
    from crawl4ai.seo_audit import SEOAnalyzer

    analyzer = SEOAnalyzer()

    # Single page audit (from CrawlResult)
    page_result = analyzer.analyze_page(crawl_result)

    # Site-wide audit (from list of CrawlResults)
    site_result = analyzer.analyze_site(crawl_results)

    # Direct HTML audit (no CrawlResult needed)
    page_result = analyzer.analyze_html(url, html)
"""

from .analyzer import SEOAnalyzer
from .checks import audit_page
from .site_checks import run_site_checks
from .models import (
    IssueSeverity,
    CheckStatus,
    PageAuditResult,
    SiteAuditResult,
    SiteAuditSummary,
    SiteIssue,
    TitleCheck,
    MetaDescriptionCheck,
    CanonicalCheck,
    RobotsCheck,
    HeadingCheck,
    HeadingInfo,
    ImageCheck,
    ImageInfo,
    LinkStats,
    OpenGraphCheck,
    TwitterCardCheck,
    StructuredDataCheck,
    StructuredDataItem,
    HreflangCheck,
    HreflangEntry,
    ContentCheck,
    URLCheck,
    MixedContentCheck,
    ViewportCheck,
    LangCheck,
    CharsetCheck,
)

__all__ = [
    # Main entry points
    "SEOAnalyzer",
    "audit_page",
    "run_site_checks",
    # Enums
    "IssueSeverity",
    "CheckStatus",
    # Page-level results
    "PageAuditResult",
    "TitleCheck",
    "MetaDescriptionCheck",
    "CanonicalCheck",
    "RobotsCheck",
    "HeadingCheck",
    "HeadingInfo",
    "ImageCheck",
    "ImageInfo",
    "LinkStats",
    "OpenGraphCheck",
    "TwitterCardCheck",
    "StructuredDataCheck",
    "StructuredDataItem",
    "HreflangCheck",
    "HreflangEntry",
    "ContentCheck",
    "URLCheck",
    "MixedContentCheck",
    "ViewportCheck",
    "LangCheck",
    "CharsetCheck",
    # Site-level results
    "SiteAuditResult",
    "SiteAuditSummary",
    "SiteIssue",
]
