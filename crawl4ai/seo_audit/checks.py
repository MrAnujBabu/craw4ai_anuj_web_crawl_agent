"""
Per-page SEO checks.

Ported from seo-audit-mcp's crawl-page.ts, browser.ts, and page-capture.ts.
Operates on raw HTML + CrawlResult metadata to produce PageAuditResult.
"""

import re
import json
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin

from lxml import html as lxml_html
from lxml.html import HtmlElement

from .models import (
    CheckStatus,
    PageAuditResult,
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


def _parse_html(raw_html: str) -> Optional[HtmlElement]:
    """Parse HTML string into an lxml tree, returning None on failure."""
    try:
        return lxml_html.fromstring(raw_html)
    except Exception:
        return None


# ─── Individual Checks ────────────────────────────────────────────────


def check_title(tree: HtmlElement) -> TitleCheck:
    """Check title tag presence and length (target: 30-65 chars)."""
    titles = tree.xpath("//title/text()")
    value = titles[0].strip() if titles else None
    if not value:
        return TitleCheck(status=CheckStatus.FAIL, note="Missing title tag")

    length = len(value)
    if 30 <= length <= 65:
        status, note = CheckStatus.PASS, "Good length"
    elif 20 <= length < 30:
        status, note = CheckStatus.WARNING, f"Slightly short ({length} chars)"
    elif 65 < length <= 80:
        status, note = CheckStatus.WARNING, f"Slightly long ({length} chars)"
    elif length < 20:
        status, note = CheckStatus.WARNING, f"Too short ({length} chars)"
    else:
        status, note = CheckStatus.WARNING, f"Too long ({length} chars, may be truncated)"

    return TitleCheck(value=value, length=length, status=status, note=note)


def check_meta_description(tree: HtmlElement) -> MetaDescriptionCheck:
    """Check meta description presence and length (target: 120-160 chars)."""
    descs = tree.xpath('//meta[@name="description"]/@content')
    value = descs[0].strip() if descs else None
    if not value:
        return MetaDescriptionCheck(
            status=CheckStatus.FAIL, note="Missing meta description"
        )

    length = len(value)
    if 120 <= length <= 160:
        status, note = CheckStatus.PASS, "Good length"
    elif 70 <= length < 120:
        status, note = CheckStatus.WARNING, f"Slightly short ({length} chars)"
    elif 160 < length <= 200:
        status, note = CheckStatus.WARNING, f"Slightly long ({length} chars)"
    elif length < 70:
        status, note = CheckStatus.WARNING, f"Too short ({length} chars)"
    else:
        status, note = CheckStatus.WARNING, f"Too long ({length} chars, will be truncated)"

    return MetaDescriptionCheck(value=value, length=length, status=status, note=note)


def check_canonical(tree: HtmlElement, page_url: str) -> CanonicalCheck:
    """Check canonical tag presence and self-referencing."""
    canonicals = tree.xpath('//link[@rel="canonical"]/@href')
    value = canonicals[0].strip() if canonicals else None
    if not value:
        return CanonicalCheck(
            status=CheckStatus.WARNING, note="Missing canonical tag"
        )

    # Normalize for comparison
    parsed_page = urlparse(page_url)
    parsed_canon = urlparse(value)
    is_self = (
        parsed_page.netloc == parsed_canon.netloc
        and parsed_page.path.rstrip("/") == parsed_canon.path.rstrip("/")
    )

    if is_self:
        return CanonicalCheck(
            value=value,
            is_self_referencing=True,
            status=CheckStatus.PASS,
            note="Self-referencing canonical",
        )
    return CanonicalCheck(
        value=value,
        is_self_referencing=False,
        status=CheckStatus.INFO,
        note=f"Points to {value}",
    )


def check_robots_meta(tree: HtmlElement) -> RobotsCheck:
    """Check robots meta tag for noindex/nofollow directives."""
    robots = tree.xpath('//meta[@name="robots"]/@content')
    value = robots[0].strip().lower() if robots else None

    if not value:
        return RobotsCheck(status=CheckStatus.PASS, note="No robots meta (defaults to index,follow)")

    is_indexable = "noindex" not in value
    is_followable = "nofollow" not in value

    if is_indexable and is_followable:
        status, note = CheckStatus.PASS, "Indexable and followable"
    elif not is_indexable:
        status, note = CheckStatus.WARNING, "Page set to noindex"
    else:
        status, note = CheckStatus.INFO, "Links set to nofollow"

    return RobotsCheck(
        value=value,
        is_indexable=is_indexable,
        is_followable=is_followable,
        status=status,
        note=note,
    )


def check_headings(tree: HtmlElement) -> HeadingCheck:
    """
    Check heading structure: H1 presence/count and hierarchy.
    Ported from seo-audit-mcp extractHeadings().
    """
    all_headings: List[HeadingInfo] = []
    h1_values: List[str] = []
    last_level = 0
    skipped: List[str] = []

    for tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        for el in tree.xpath(f"//{tag}"):
            text = (el.text_content() or "").strip()
            level = int(tag[1])
            all_headings.append(HeadingInfo(tag=tag, text=text))
            if tag == "h1":
                h1_values.append(text)
            if last_level and level > last_level + 1:
                skipped.append(f"h{last_level} -> h{level}")
            last_level = level

    # Re-sort by document order via xpath
    ordered_headings: List[HeadingInfo] = []
    for el in tree.xpath("//*[self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6]"):
        tag = el.tag.lower()
        text = (el.text_content() or "").strip()
        ordered_headings.append(HeadingInfo(tag=tag, text=text))

    # Recompute skipped levels from ordered headings
    skipped = []
    last_level = 0
    for h in ordered_headings:
        level = int(h.tag[1])
        if last_level and level > last_level + 1:
            skipped.append(f"h{last_level} -> h{level}")
        last_level = level

    h1_count = len(h1_values)
    hierarchy_valid = len(skipped) == 0

    if h1_count == 0:
        status, note = CheckStatus.FAIL, "Missing H1 tag"
    elif h1_count > 1:
        status, note = CheckStatus.WARNING, f"Multiple H1 tags ({h1_count})"
    elif not hierarchy_valid:
        status, note = CheckStatus.WARNING, f"Skipped heading levels: {', '.join(skipped)}"
    elif h1_values and len(h1_values[0]) > 70:
        status, note = CheckStatus.WARNING, f"H1 too long ({len(h1_values[0])} chars)"
    else:
        status, note = CheckStatus.PASS, "Good heading structure"

    return HeadingCheck(
        h1_count=h1_count,
        h1_values=h1_values,
        hierarchy_valid=hierarchy_valid,
        skipped_levels=skipped,
        all_headings=ordered_headings,
        status=status,
        note=note,
    )


def check_images(tree: HtmlElement) -> ImageCheck:
    """
    Check images for alt text.
    Ported from seo-audit-mcp extractImages().
    """
    images: List[ImageInfo] = []
    missing_alt = 0
    empty_alt = 0

    for img in tree.xpath("//img"):
        src = img.get("src", "") or img.get("data-src", "")
        alt = img.get("alt")
        has_alt = alt is not None
        is_empty = has_alt and alt.strip() == ""
        is_lazy = bool(
            img.get("loading") == "lazy"
            or img.get("data-src")
            or img.get("data-lazy")
        )
        width = _int_or_none(img.get("width"))
        height = _int_or_none(img.get("height"))

        if not has_alt:
            missing_alt += 1
        elif is_empty:
            empty_alt += 1

        images.append(
            ImageInfo(
                src=src,
                alt=alt,
                has_alt=has_alt,
                is_lazy_loaded=is_lazy,
                width=width,
                height=height,
            )
        )

    total = len(images)
    if missing_alt > 0:
        status = CheckStatus.WARNING
        note = f"{missing_alt}/{total} images missing alt text"
    elif empty_alt > 0:
        status = CheckStatus.INFO
        note = f"{empty_alt}/{total} images have empty alt text"
    else:
        status = CheckStatus.PASS
        note = f"All {total} images have alt text" if total else "No images found"

    return ImageCheck(
        total=total,
        missing_alt=missing_alt,
        empty_alt=empty_alt,
        images=images,
        status=status,
        note=note,
    )


def check_links(
    tree: HtmlElement, page_url: str
) -> LinkStats:
    """
    Categorize internal/external/nofollow links.
    Ported from seo-audit-mcp extractLinks().
    """
    parsed_page = urlparse(page_url)
    page_domain = parsed_page.netloc.lower()

    internal = 0
    external = 0
    nofollow = 0

    for a in tree.xpath("//a[@href]"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue

        rel = (a.get("rel") or "").lower()
        if "nofollow" in rel:
            nofollow += 1

        absolute = urljoin(page_url, href)
        link_domain = urlparse(absolute).netloc.lower()

        if link_domain == page_domain:
            internal += 1
        else:
            external += 1

    if internal == 0:
        status = CheckStatus.WARNING
        note = "No internal links found"
    else:
        status = CheckStatus.PASS
        note = f"{internal} internal, {external} external, {nofollow} nofollow"

    return LinkStats(
        internal_count=internal,
        external_count=external,
        nofollow_count=nofollow,
        status=status,
        note=note,
    )


def check_open_graph(tree: HtmlElement) -> OpenGraphCheck:
    """
    Check Open Graph tags.
    Ported from seo-audit-mcp extractOpenGraph().
    """
    og_tags = {
        "og:title": None,
        "og:description": None,
        "og:image": None,
        "og:type": None,
        "og:url": None,
    }
    present: List[str] = []
    missing: List[str] = []

    for key in og_tags:
        vals = tree.xpath(f'//meta[@property="{key}"]/@content')
        if vals:
            og_tags[key] = vals[0].strip()
            present.append(key)
        else:
            missing.append(key)

    essential_missing = [t for t in missing if t in ("og:title", "og:description", "og:image")]
    if not present:
        status, note = CheckStatus.FAIL, "No Open Graph tags found"
    elif essential_missing:
        status, note = CheckStatus.WARNING, f"Missing: {', '.join(essential_missing)}"
    else:
        status, note = CheckStatus.PASS, "All essential OG tags present"

    return OpenGraphCheck(
        og_title=og_tags["og:title"],
        og_description=og_tags["og:description"],
        og_image=og_tags["og:image"],
        og_type=og_tags["og:type"],
        og_url=og_tags["og:url"],
        present_tags=present,
        missing_tags=missing,
        status=status,
        note=note,
    )


def check_twitter_card(tree: HtmlElement) -> TwitterCardCheck:
    """
    Check Twitter Card tags.
    Ported from seo-audit-mcp extractTwitterCard().
    """
    tc_tags = {
        "twitter:card": None,
        "twitter:title": None,
        "twitter:description": None,
        "twitter:image": None,
    }
    present: List[str] = []
    missing: List[str] = []

    for key in tc_tags:
        vals = tree.xpath(f'//meta[@name="{key}"]/@content')
        if vals:
            tc_tags[key] = vals[0].strip()
            present.append(key)
        else:
            missing.append(key)

    if not present:
        status, note = CheckStatus.INFO, "No Twitter Card tags found"
    elif "twitter:card" not in present:
        status, note = CheckStatus.WARNING, "Missing twitter:card type"
    else:
        status, note = CheckStatus.PASS, f"Twitter Card: {tc_tags['twitter:card']}"

    return TwitterCardCheck(
        card_type=tc_tags["twitter:card"],
        title=tc_tags["twitter:title"],
        description=tc_tags["twitter:description"],
        image=tc_tags["twitter:image"],
        present_tags=present,
        missing_tags=missing,
        status=status,
        note=note,
    )


def check_structured_data(tree: HtmlElement) -> StructuredDataCheck:
    """
    Extract and validate JSON-LD structured data.
    Ported from seo-audit-mcp extractJsonLd() + analyzeStructuredData().
    """
    items: List[StructuredDataItem] = []
    schema_types: List[str] = []
    has_json_ld = False

    scripts = tree.xpath('//script[@type="application/ld+json"]/text()')
    for script_text in scripts:
        try:
            data = json.loads(script_text.strip())
        except (json.JSONDecodeError, ValueError):
            items.append(
                StructuredDataItem(
                    schema_type="unknown",
                    errors=["Invalid JSON-LD: parse error"],
                )
            )
            has_json_ld = True
            continue

        has_json_ld = True
        # Handle @graph arrays
        entries = data.get("@graph", [data]) if isinstance(data, dict) else [data]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            schema_type = entry.get("@type", "unknown")
            if isinstance(schema_type, list):
                schema_type = ", ".join(schema_type)
            schema_types.append(schema_type)

            errors, warnings = _validate_structured_data(schema_type, entry)
            items.append(
                StructuredDataItem(
                    schema_type=schema_type,
                    properties=entry,
                    errors=errors,
                    warnings=warnings,
                )
            )

    total_errors = sum(len(i.errors) for i in items)
    if not has_json_ld:
        status, note = CheckStatus.INFO, "No JSON-LD structured data found"
    elif total_errors > 0:
        status, note = CheckStatus.WARNING, f"{total_errors} structured data errors"
    else:
        status, note = CheckStatus.PASS, f"Found: {', '.join(schema_types)}"

    return StructuredDataCheck(
        items=items,
        has_json_ld=has_json_ld,
        schema_types=schema_types,
        status=status,
        note=note,
    )


def _validate_structured_data(
    schema_type: str, data: Dict[str, Any]
) -> Tuple[List[str], List[str]]:
    """Validate structured data entry. Returns (errors, warnings)."""
    errors: List[str] = []
    warnings: List[str] = []

    if "JobPosting" in schema_type:
        # Required fields per Google
        required = ["title", "description", "datePosted", "hiringOrganization", "jobLocation"]
        for field in required:
            if field not in data:
                errors.append(f"JobPosting missing required field: {field}")
        # Recommended fields
        recommended = ["validThrough", "baseSalary", "employmentType", "identifier", "directApply"]
        for field in recommended:
            if field not in data:
                warnings.append(f"JobPosting missing recommended field: {field}")
        # Check expiration
        valid_through = data.get("validThrough")
        if valid_through and isinstance(valid_through, str):
            try:
                from datetime import datetime
                exp = datetime.fromisoformat(valid_through.replace("Z", "+00:00"))
                if exp < datetime.now(exp.tzinfo):
                    errors.append("JobPosting has expired (validThrough in the past)")
            except (ValueError, TypeError):
                pass

    elif "Organization" in schema_type:
        if "name" not in data:
            warnings.append("Organization missing 'name'")
        if "url" not in data:
            warnings.append("Organization missing 'url'")

    elif "BreadcrumbList" in schema_type:
        items = data.get("itemListElement", [])
        if not items:
            warnings.append("BreadcrumbList has no items")

    elif "WebSite" in schema_type:
        if "potentialAction" not in data:
            warnings.append("WebSite missing SearchAction (potentialAction)")

    return errors, warnings


def check_hreflang(tree: HtmlElement) -> HreflangCheck:
    """Check hreflang tags for multilingual sites."""
    entries: List[HreflangEntry] = []
    has_x_default = False

    for link in tree.xpath('//link[@rel="alternate"][@hreflang]'):
        lang = (link.get("hreflang") or "").strip()
        href = (link.get("href") or "").strip()
        if lang and href:
            entries.append(HreflangEntry(lang=lang, href=href))
            if lang == "x-default":
                has_x_default = True

    if not entries:
        return HreflangCheck(status=CheckStatus.INFO, note="No hreflang tags (single language site)")

    if not has_x_default:
        status, note = CheckStatus.WARNING, f"{len(entries)} hreflang tags but missing x-default"
    else:
        status, note = CheckStatus.PASS, f"{len(entries)} hreflang tags with x-default"

    return HreflangCheck(
        entries=entries, has_x_default=has_x_default, status=status, note=note
    )


def check_content(tree: HtmlElement) -> ContentCheck:
    """Check page content word count (flag thin content <300 words).

    Pages with forms (login, checkout, contact, etc.) use a lower threshold
    of 100 words since they are inherently transactional.
    """
    body = tree.xpath("//body")
    if not body:
        return ContentCheck(status=CheckStatus.WARNING, note="No body content found")

    # Remove script and style elements
    text_parts = []
    for el in body[0].iter():
        if el.tag in ("script", "style", "noscript"):
            continue
        if el.text:
            text_parts.append(el.text)
        if el.tail:
            text_parts.append(el.tail)

    text = " ".join(text_parts)
    words = len(text.split())

    # Lower threshold for form/transactional pages
    has_form = bool(tree.xpath("//form"))
    thin_threshold = 100 if has_form else 300

    if words < thin_threshold:
        label = f"Thin content ({words} words, <{thin_threshold})"
        if has_form:
            label += " — form page"
        status, note = CheckStatus.WARNING, label
    elif words < 600:
        status, note = CheckStatus.INFO, f"{words} words (consider expanding)"
    else:
        status, note = CheckStatus.PASS, f"{words} words"

    return ContentCheck(word_count=words, status=status, note=note)


def check_url_structure(url: str) -> URLCheck:
    """Check URL quality: length, special chars, hyphens vs underscores, case."""
    parsed = urlparse(url)
    path = parsed.path

    length = len(url)
    has_special = bool(re.search(r"[^a-zA-Z0-9/_\-.]", path))
    uses_hyphens = "-" in path
    has_underscores = "_" in path
    has_uppercase = path != path.lower()

    issues = []
    if length > 100:
        issues.append(f"URL too long ({length} chars)")
    if has_special:
        issues.append("Contains special characters")
    if has_underscores:
        issues.append("Uses underscores instead of hyphens")
    if has_uppercase:
        issues.append("Contains uppercase characters")

    if issues:
        status = CheckStatus.WARNING
        note = "; ".join(issues)
    else:
        status = CheckStatus.PASS
        note = "Clean URL structure"

    return URLCheck(
        url=url,
        length=length,
        has_special_chars=has_special,
        uses_hyphens=uses_hyphens,
        has_uppercase=has_uppercase,
        status=status,
        note=note,
    )


def check_mixed_content(tree: HtmlElement, page_url: str) -> MixedContentCheck:
    """
    Detect mixed content (HTTP resources on HTTPS pages).
    Ported from seo-audit-mcp checkMixedContent().
    """
    if not page_url.startswith("https://"):
        return MixedContentCheck(status=CheckStatus.PASS, note="Page not served over HTTPS")

    insecure: List[str] = []

    # Check common resource tags
    for tag, attr in [
        ("img", "src"),
        ("script", "src"),
        ("link", "href"),
        ("video", "src"),
        ("audio", "src"),
        ("source", "src"),
        ("iframe", "src"),
    ]:
        for el in tree.xpath(f"//{tag}[@{attr}]"):
            val = (el.get(attr) or "").strip()
            if val.startswith("http://"):
                insecure.append(val)

    if insecure:
        return MixedContentCheck(
            has_mixed_content=True,
            insecure_resources=insecure[:20],  # cap to avoid noise
            status=CheckStatus.WARNING,
            note=f"{len(insecure)} insecure resource(s) on HTTPS page",
        )
    return MixedContentCheck(status=CheckStatus.PASS, note="No mixed content detected")


def check_viewport(tree: HtmlElement) -> ViewportCheck:
    """Check viewport meta tag for mobile-friendliness."""
    viewports = tree.xpath('//meta[@name="viewport"]/@content')
    value = viewports[0].strip() if viewports else None
    if not value:
        return ViewportCheck(status=CheckStatus.FAIL, note="Missing viewport meta tag")
    return ViewportCheck(value=value, status=CheckStatus.PASS, note="Viewport configured")


def check_lang(tree: HtmlElement) -> LangCheck:
    """Check html lang attribute."""
    langs = tree.xpath("//html/@lang")
    value = langs[0].strip() if langs else None
    if not value:
        return LangCheck(status=CheckStatus.WARNING, note="Missing lang attribute on <html>")
    return LangCheck(value=value, status=CheckStatus.PASS, note=f"Language: {value}")


def check_charset(tree: HtmlElement) -> CharsetCheck:
    """Check charset declaration."""
    # <meta charset="utf-8">
    charsets = tree.xpath("//meta/@charset")
    if charsets:
        return CharsetCheck(
            value=charsets[0].strip(),
            status=CheckStatus.PASS,
            note=f"Charset: {charsets[0].strip()}",
        )
    # <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    content_types = tree.xpath('//meta[@http-equiv="Content-Type"]/@content')
    if content_types:
        match = re.search(r"charset=([^\s;]+)", content_types[0])
        if match:
            return CharsetCheck(
                value=match.group(1),
                status=CheckStatus.PASS,
                note=f"Charset: {match.group(1)}",
            )
    return CharsetCheck(status=CheckStatus.WARNING, note="No charset declaration found")


# ─── Main Per-Page Audit ──────────────────────────────────────────────


def audit_page(url: str, raw_html: str, status_code: Optional[int] = None) -> PageAuditResult:
    """
    Run all per-page SEO checks on the given HTML.

    Args:
        url: The page URL.
        raw_html: The full HTML content of the page.
        status_code: HTTP status code (if available).

    Returns:
        PageAuditResult with all check results populated.
    """
    tree = _parse_html(raw_html)
    if tree is None:
        return PageAuditResult(
            url=url,
            status_code=status_code,
            title=TitleCheck(status=CheckStatus.FAIL, note="Could not parse HTML"),
        )

    return PageAuditResult(
        url=url,
        status_code=status_code,
        title=check_title(tree),
        meta_description=check_meta_description(tree),
        canonical=check_canonical(tree, url),
        robots=check_robots_meta(tree),
        headings=check_headings(tree),
        images=check_images(tree),
        links=check_links(tree, url),
        open_graph=check_open_graph(tree),
        twitter_card=check_twitter_card(tree),
        structured_data=check_structured_data(tree),
        hreflang=check_hreflang(tree),
        content=check_content(tree),
        url_check=check_url_structure(url),
        mixed_content=check_mixed_content(tree, url),
        viewport=check_viewport(tree),
        lang=check_lang(tree),
        charset=check_charset(tree),
    )


# ─── Helpers ──────────────────────────────────────────────────────────


def _int_or_none(val: Optional[str]) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
