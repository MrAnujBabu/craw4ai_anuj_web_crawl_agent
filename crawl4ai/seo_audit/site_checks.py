"""
Site-wide SEO checks.

Ported from seo-audit-mcp's crawl-site.ts generateCrawlSummary() logic.
Operates on a collection of PageAuditResult objects to find cross-page issues
like duplicate titles, orphan pages, deep link structures, etc.
"""

from collections import defaultdict
from typing import List, Dict, Set, Optional
from urllib.parse import urlparse

from .models import (
    IssueSeverity,
    CheckStatus,
    PageAuditResult,
    SiteIssue,
    SiteAuditSummary,
    SiteAuditResult,
)


def run_site_checks(
    page_results: Dict[str, PageAuditResult],
    internal_link_graph: Optional[Dict[str, List[str]]] = None,
) -> SiteAuditResult:
    """
    Run all site-wide SEO checks across a set of audited pages.

    Args:
        page_results: Mapping of URL -> PageAuditResult.
        internal_link_graph: Optional mapping of URL -> list of URLs it links to.

    Returns:
        SiteAuditResult with summary, issues, and per-page details.
    """
    critical: List[SiteIssue] = []
    warnings: List[SiteIssue] = []
    info: List[SiteIssue] = []

    # ── Duplicate titles ──────────────────────────────────────────────
    issue = _check_duplicate_titles(page_results)
    if issue:
        (warnings if issue.severity == IssueSeverity.WARNING else critical).append(issue)

    # ── Duplicate meta descriptions ───────────────────────────────────
    issue = _check_duplicate_descriptions(page_results)
    if issue:
        (warnings if issue.severity == IssueSeverity.WARNING else critical).append(issue)

    # ── Missing H1 tags ──────────────────────────────────────────────
    issue = _check_missing_h1(page_results)
    if issue:
        critical.append(issue)

    # ── Missing titles ────────────────────────────────────────────────
    issue = _check_missing_titles(page_results)
    if issue:
        critical.append(issue)

    # ── Missing meta descriptions ─────────────────────────────────────
    issue = _check_missing_descriptions(page_results)
    if issue:
        warnings.append(issue)

    # ── Missing canonical tags ────────────────────────────────────────
    issue = _check_missing_canonicals(page_results)
    if issue:
        warnings.append(issue)

    # ── Missing Open Graph ────────────────────────────────────────────
    issue = _check_missing_open_graph(page_results)
    if issue:
        info.append(issue)

    # ── Thin content ──────────────────────────────────────────────────
    issue = _check_thin_content(page_results)
    if issue:
        warnings.append(issue)

    # ── Missing viewport ──────────────────────────────────────────────
    issue = _check_missing_viewport(page_results)
    if issue:
        critical.append(issue)

    # ── Mixed content ─────────────────────────────────────────────────
    issue = _check_site_mixed_content(page_results)
    if issue:
        warnings.append(issue)

    # ── Image alt text ────────────────────────────────────────────────
    issue = _check_images_missing_alt(page_results)
    if issue:
        warnings.append(issue)

    # ── Orphan pages (if link graph available) ────────────────────────
    if internal_link_graph is not None:
        issue = _check_orphan_pages(page_results, internal_link_graph)
        if issue:
            warnings.append(issue)

        issue = _check_deep_pages(page_results, internal_link_graph)
        if issue:
            info.append(issue)

    # ── Compute score and summary ─────────────────────────────────────
    n_critical = len(critical)
    n_warning = len(warnings)
    n_info = len(info)

    # Score: start at 100, deduct per issue
    score = max(0, 100 - (n_critical * 15) - (n_warning * 5) - (n_info * 1))

    summary = SiteAuditSummary(
        pages_audited=len(page_results),
        issues_critical=n_critical,
        issues_warning=n_warning,
        issues_info=n_info,
        score=score,
    )

    return SiteAuditResult(
        summary=summary,
        critical=critical,
        warnings=warnings,
        info=info,
        page_details=page_results,
    )


# ─── Individual Site-Wide Checks ──────────────────────────────────────


def _check_duplicate_titles(pages: Dict[str, PageAuditResult]) -> Optional[SiteIssue]:
    title_map: Dict[str, List[str]] = defaultdict(list)
    for url, result in pages.items():
        # Skip redirect pages (301/302/etc.) — they share the destination's title
        if result.status_code and 300 <= result.status_code < 400:
            continue
        if result.title.value:
            title_map[result.title.value.lower()].append(url)

    duplicates = {t: urls for t, urls in title_map.items() if len(urls) > 1}
    if not duplicates:
        return None

    affected = []
    for urls in duplicates.values():
        affected.extend(urls)

    return SiteIssue(
        issue_type="duplicate_titles",
        severity=IssueSeverity.WARNING,
        affected_pages=affected,
        description=f"{len(duplicates)} duplicate title(s) across {len(affected)} pages",
        fix="Ensure each page has a unique, descriptive title tag",
    )


def _check_duplicate_descriptions(pages: Dict[str, PageAuditResult]) -> Optional[SiteIssue]:
    desc_map: Dict[str, List[str]] = defaultdict(list)
    for url, result in pages.items():
        # Skip redirect pages (301/302/etc.) — they share the destination's description
        if result.status_code and 300 <= result.status_code < 400:
            continue
        if result.meta_description.value:
            desc_map[result.meta_description.value.lower()].append(url)

    duplicates = {d: urls for d, urls in desc_map.items() if len(urls) > 1}
    if not duplicates:
        return None

    affected = []
    for urls in duplicates.values():
        affected.extend(urls)

    return SiteIssue(
        issue_type="duplicate_meta_descriptions",
        severity=IssueSeverity.WARNING,
        affected_pages=affected,
        description=f"{len(duplicates)} duplicate meta description(s) across {len(affected)} pages",
        fix="Write unique meta descriptions for each page",
    )


def _check_missing_h1(pages: Dict[str, PageAuditResult]) -> Optional[SiteIssue]:
    affected = [url for url, r in pages.items() if r.headings.h1_count == 0]
    if not affected:
        return None
    return SiteIssue(
        issue_type="missing_h1",
        severity=IssueSeverity.CRITICAL,
        affected_pages=affected,
        description=f"{len(affected)} page(s) missing H1 tag",
        fix="Add a single, descriptive H1 tag to each page",
    )


def _check_missing_titles(pages: Dict[str, PageAuditResult]) -> Optional[SiteIssue]:
    affected = [url for url, r in pages.items() if not r.title.value]
    if not affected:
        return None
    return SiteIssue(
        issue_type="missing_title",
        severity=IssueSeverity.CRITICAL,
        affected_pages=affected,
        description=f"{len(affected)} page(s) missing title tag",
        fix="Add a descriptive title tag (50-60 chars) to each page",
    )


def _check_missing_descriptions(pages: Dict[str, PageAuditResult]) -> Optional[SiteIssue]:
    affected = [url for url, r in pages.items() if not r.meta_description.value]
    if not affected:
        return None
    return SiteIssue(
        issue_type="missing_meta_description",
        severity=IssueSeverity.WARNING,
        affected_pages=affected,
        description=f"{len(affected)} page(s) missing meta description",
        fix="Write a compelling meta description (150-160 chars) for each page",
    )


def _check_missing_canonicals(pages: Dict[str, PageAuditResult]) -> Optional[SiteIssue]:
    affected = [url for url, r in pages.items() if not r.canonical.value]
    if not affected:
        return None
    return SiteIssue(
        issue_type="missing_canonical",
        severity=IssueSeverity.WARNING,
        affected_pages=affected,
        description=f"{len(affected)} page(s) missing canonical tag",
        fix="Add self-referencing canonical tags to prevent duplicate content issues",
    )


def _check_missing_open_graph(pages: Dict[str, PageAuditResult]) -> Optional[SiteIssue]:
    affected = [url for url, r in pages.items() if r.open_graph.status == CheckStatus.FAIL]
    if not affected:
        return None
    return SiteIssue(
        issue_type="missing_open_graph",
        severity=IssueSeverity.INFO,
        affected_pages=affected,
        description=f"{len(affected)} page(s) missing Open Graph tags",
        fix="Add og:title, og:description, og:image for better social sharing",
    )


def _check_thin_content(pages: Dict[str, PageAuditResult]) -> Optional[SiteIssue]:
    # Only flag pages whose per-page content check already reported a warning.
    # This respects the lower threshold for form/transactional pages.
    affected = [url for url, r in pages.items() if r.content.status == CheckStatus.WARNING]
    if not affected:
        return None
    return SiteIssue(
        issue_type="thin_content",
        severity=IssueSeverity.WARNING,
        affected_pages=affected,
        description=f"{len(affected)} page(s) with thin content",
        fix="Expand content with relevant, valuable information (form/transactional pages have a lower threshold)",
    )


def _check_missing_viewport(pages: Dict[str, PageAuditResult]) -> Optional[SiteIssue]:
    affected = [url for url, r in pages.items() if r.viewport.status == CheckStatus.FAIL]
    if not affected:
        return None
    return SiteIssue(
        issue_type="missing_viewport",
        severity=IssueSeverity.CRITICAL,
        affected_pages=affected,
        description=f"{len(affected)} page(s) missing viewport meta tag",
        fix="Add <meta name='viewport' content='width=device-width, initial-scale=1'>",
    )


def _check_site_mixed_content(pages: Dict[str, PageAuditResult]) -> Optional[SiteIssue]:
    affected = [url for url, r in pages.items() if r.mixed_content.has_mixed_content]
    if not affected:
        return None
    return SiteIssue(
        issue_type="mixed_content",
        severity=IssueSeverity.WARNING,
        affected_pages=affected,
        description=f"{len(affected)} page(s) with mixed content (HTTP on HTTPS)",
        fix="Update all resource URLs to use HTTPS",
    )


def _check_images_missing_alt(pages: Dict[str, PageAuditResult]) -> Optional[SiteIssue]:
    affected = [url for url, r in pages.items() if r.images.missing_alt > 0]
    if not affected:
        return None

    total_missing = sum(r.images.missing_alt for r in pages.values())
    return SiteIssue(
        issue_type="images_missing_alt",
        severity=IssueSeverity.WARNING,
        affected_pages=affected,
        description=f"{total_missing} image(s) across {len(affected)} page(s) missing alt text",
        fix="Add descriptive alt text to all images for accessibility and SEO",
    )


def _check_orphan_pages(
    pages: Dict[str, PageAuditResult],
    link_graph: Dict[str, List[str]],
) -> Optional[SiteIssue]:
    """Find pages that no other page links to."""
    all_urls = set(pages.keys())
    linked_to: Set[str] = set()
    for targets in link_graph.values():
        linked_to.update(targets)

    # Exclude homepage (first URL or root path)
    orphans = []
    for url in all_urls:
        parsed = urlparse(url)
        # Skip the homepage
        if parsed.path in ("", "/"):
            continue
        if url not in linked_to:
            orphans.append(url)

    if not orphans:
        return None
    return SiteIssue(
        issue_type="orphan_pages",
        severity=IssueSeverity.WARNING,
        affected_pages=orphans,
        description=f"{len(orphans)} orphan page(s) with no internal links pointing to them",
        fix="Add internal links from relevant pages to improve discoverability",
    )


def _check_deep_pages(
    pages: Dict[str, PageAuditResult],
    link_graph: Dict[str, List[str]],
) -> Optional[SiteIssue]:
    """Find pages >3 clicks from the homepage (BFS depth)."""
    if not link_graph:
        return None

    # Find homepage
    homepage = None
    for url in link_graph:
        parsed = urlparse(url)
        if parsed.path in ("", "/"):
            homepage = url
            break
    if not homepage:
        homepage = next(iter(link_graph), None)
    if not homepage:
        return None

    # BFS from homepage
    depths: Dict[str, int] = {homepage: 0}
    queue = [homepage]
    visited = {homepage}

    while queue:
        current = queue.pop(0)
        current_depth = depths[current]
        for linked in link_graph.get(current, []):
            if linked not in visited and linked in pages:
                visited.add(linked)
                depths[linked] = current_depth + 1
                queue.append(linked)

    deep = [url for url, depth in depths.items() if depth > 3]
    # Also include pages unreachable via link graph
    unreachable = [url for url in pages if url not in depths]
    deep.extend(unreachable)

    if not deep:
        return None
    return SiteIssue(
        issue_type="deep_pages",
        severity=IssueSeverity.INFO,
        affected_pages=deep,
        description=f"{len(deep)} page(s) are >3 clicks from homepage or unreachable via internal links",
        fix="Improve internal linking to keep important pages within 3 clicks of homepage",
    )
