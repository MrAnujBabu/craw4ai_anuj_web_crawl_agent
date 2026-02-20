"""
SEO Audit data models.

Ported from RichardDillman/seo-audit-mcp TypeScript types to Pydantic models
for integration with crawl4ai's CrawlResult pipeline.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from enum import Enum


class IssueSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    INFO = "info"


# ─── Per-Page Check Results ───────────────────────────────────────────


class TitleCheck(BaseModel):
    value: Optional[str] = None
    length: int = 0
    status: CheckStatus = CheckStatus.FAIL
    note: str = ""


class MetaDescriptionCheck(BaseModel):
    value: Optional[str] = None
    length: int = 0
    status: CheckStatus = CheckStatus.FAIL
    note: str = ""


class CanonicalCheck(BaseModel):
    value: Optional[str] = None
    is_self_referencing: bool = False
    status: CheckStatus = CheckStatus.FAIL
    note: str = ""


class RobotsCheck(BaseModel):
    value: Optional[str] = None
    is_indexable: bool = True
    is_followable: bool = True
    status: CheckStatus = CheckStatus.PASS
    note: str = ""


class HeadingInfo(BaseModel):
    tag: str = ""
    text: str = ""


class HeadingCheck(BaseModel):
    h1_count: int = 0
    h1_values: List[str] = Field(default_factory=list)
    hierarchy_valid: bool = True
    skipped_levels: List[str] = Field(default_factory=list)
    all_headings: List[HeadingInfo] = Field(default_factory=list)
    status: CheckStatus = CheckStatus.FAIL
    note: str = ""


class ImageInfo(BaseModel):
    src: str = ""
    alt: Optional[str] = None
    has_alt: bool = False
    is_lazy_loaded: bool = False
    width: Optional[int] = None
    height: Optional[int] = None


class ImageCheck(BaseModel):
    total: int = 0
    missing_alt: int = 0
    empty_alt: int = 0
    images: List[ImageInfo] = Field(default_factory=list)
    status: CheckStatus = CheckStatus.PASS
    note: str = ""


class LinkStats(BaseModel):
    internal_count: int = 0
    external_count: int = 0
    nofollow_count: int = 0
    status: CheckStatus = CheckStatus.PASS
    note: str = ""


class OpenGraphCheck(BaseModel):
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    og_type: Optional[str] = None
    og_url: Optional[str] = None
    present_tags: List[str] = Field(default_factory=list)
    missing_tags: List[str] = Field(default_factory=list)
    status: CheckStatus = CheckStatus.FAIL
    note: str = ""


class TwitterCardCheck(BaseModel):
    card_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    present_tags: List[str] = Field(default_factory=list)
    missing_tags: List[str] = Field(default_factory=list)
    status: CheckStatus = CheckStatus.PASS
    note: str = ""


class StructuredDataItem(BaseModel):
    schema_type: str = ""
    properties: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class StructuredDataCheck(BaseModel):
    items: List[StructuredDataItem] = Field(default_factory=list)
    has_json_ld: bool = False
    schema_types: List[str] = Field(default_factory=list)
    status: CheckStatus = CheckStatus.INFO
    note: str = ""


class HreflangEntry(BaseModel):
    lang: str = ""
    href: str = ""


class HreflangCheck(BaseModel):
    entries: List[HreflangEntry] = Field(default_factory=list)
    has_x_default: bool = False
    status: CheckStatus = CheckStatus.INFO
    note: str = ""


class ContentCheck(BaseModel):
    word_count: int = 0
    status: CheckStatus = CheckStatus.PASS
    note: str = ""


class URLCheck(BaseModel):
    url: str = ""
    length: int = 0
    has_special_chars: bool = False
    uses_hyphens: bool = True
    has_uppercase: bool = False
    status: CheckStatus = CheckStatus.PASS
    note: str = ""


class MixedContentCheck(BaseModel):
    has_mixed_content: bool = False
    insecure_resources: List[str] = Field(default_factory=list)
    status: CheckStatus = CheckStatus.PASS
    note: str = ""


class ViewportCheck(BaseModel):
    value: Optional[str] = None
    status: CheckStatus = CheckStatus.FAIL
    note: str = ""


class LangCheck(BaseModel):
    value: Optional[str] = None
    status: CheckStatus = CheckStatus.INFO
    note: str = ""


class CharsetCheck(BaseModel):
    value: Optional[str] = None
    status: CheckStatus = CheckStatus.PASS
    note: str = ""


# ─── Page-Level Audit Result ─────────────────────────────────────────


class PageAuditResult(BaseModel):
    url: str
    status_code: Optional[int] = None
    title: TitleCheck = Field(default_factory=TitleCheck)
    meta_description: MetaDescriptionCheck = Field(default_factory=MetaDescriptionCheck)
    canonical: CanonicalCheck = Field(default_factory=CanonicalCheck)
    robots: RobotsCheck = Field(default_factory=RobotsCheck)
    headings: HeadingCheck = Field(default_factory=HeadingCheck)
    images: ImageCheck = Field(default_factory=ImageCheck)
    links: LinkStats = Field(default_factory=LinkStats)
    open_graph: OpenGraphCheck = Field(default_factory=OpenGraphCheck)
    twitter_card: TwitterCardCheck = Field(default_factory=TwitterCardCheck)
    structured_data: StructuredDataCheck = Field(default_factory=StructuredDataCheck)
    hreflang: HreflangCheck = Field(default_factory=HreflangCheck)
    content: ContentCheck = Field(default_factory=ContentCheck)
    url_check: URLCheck = Field(default_factory=URLCheck)
    mixed_content: MixedContentCheck = Field(default_factory=MixedContentCheck)
    viewport: ViewportCheck = Field(default_factory=ViewportCheck)
    lang: LangCheck = Field(default_factory=LangCheck)
    charset: CharsetCheck = Field(default_factory=CharsetCheck)

    @property
    def critical_issues(self) -> List[str]:
        issues = []
        for field_name in self.model_fields:
            val = getattr(self, field_name)
            if isinstance(val, BaseModel) and hasattr(val, "status"):
                if val.status == CheckStatus.FAIL:
                    issues.append(f"{field_name}: {val.note}")
        return issues

    @property
    def warnings(self) -> List[str]:
        warns = []
        for field_name in self.model_fields:
            val = getattr(self, field_name)
            if isinstance(val, BaseModel) and hasattr(val, "status"):
                if val.status == CheckStatus.WARNING:
                    warns.append(f"{field_name}: {val.note}")
        return warns


# ─── Site-Wide Issue ──────────────────────────────────────────────────


class SiteIssue(BaseModel):
    issue_type: str
    severity: IssueSeverity
    affected_pages: List[str] = Field(default_factory=list)
    description: str = ""
    fix: str = ""


# ─── Site-Wide Audit Summary ─────────────────────────────────────────


class SiteAuditSummary(BaseModel):
    pages_audited: int = 0
    issues_critical: int = 0
    issues_warning: int = 0
    issues_info: int = 0
    score: int = 0  # 0-100


class SiteAuditResult(BaseModel):
    summary: SiteAuditSummary = Field(default_factory=SiteAuditSummary)
    critical: List[SiteIssue] = Field(default_factory=list)
    warnings: List[SiteIssue] = Field(default_factory=list)
    info: List[SiteIssue] = Field(default_factory=list)
    page_details: Dict[str, PageAuditResult] = Field(default_factory=dict)
