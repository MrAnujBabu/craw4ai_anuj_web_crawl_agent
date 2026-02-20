# AI-Powered SEO Platform — Build Plan & Requirements

## What We're Building

A unified SEO platform that replaces $400+/mo in enterprise tools (Ahrefs, SEMrush, Screaming Frog) with a ~$30-45/mo stack powered by Claude as the reasoning engine and MCP as the integration layer. The key differentiator: Claude sees all data sources simultaneously and can correlate insights across them — something no existing tool can do.

---

## Current State (What You Already Have)

| Component | Status | What It Does |
|-----------|--------|-------------|
| Claude Pro | ✅ Active | AI analysis, strategy, MCP client |
| SEO-MCP (DataForSEO) | ✅ Connected | Keywords, backlinks, SERP, Lighthouse, content parsing |
| Canva MCP | ✅ Connected | Visual content creation from within Claude |
| Cloudflare Workers Paid | ✅ Active ($5/mo) | MCP server hosting |
| SEO Analysis Project | ✅ Built | System prompt + workflow for full SEO audits |

---

## What We're Adding

### Component 1: Site Crawler (Cloudflare Container + Crawl4AI)
**Gap filled:** Full site crawling — discover all pages, extract content, find technical issues

### Component 2: SEO Audit Layer
**Gap filled:** Automated technical SEO checks on crawled pages

### Component 3: Google Analytics 4 MCP
**Gap filled:** Traffic data, user behavior, conversion metrics

### Component 4: Google Search Console MCP
**Gap filled:** Search queries, impressions, clicks, CTR, position data, indexing status

### Component 5 (Optional): Google Business Profile via Zapier MCP
**Gap filled:** Local SEO management — posts, reviews, Q&A

---

## Architecture

```
                         Claude Pro (claude.ai)
                              │
                    ┌─────────┼──────────┐
                    │         │          │
               MCP SSE    MCP SSE    MCP (stdio/remote)
                    │         │          │
         ┌─────────┘    ┌────┘    ┌─────┘──────┐
         ▼              ▼         ▼            ▼
   ┌──────────┐  ┌──────────┐  ┌─────┐   ┌──────┐
   │ SEO-MCP  │  │ Crawler  │  │ GA4 │   │ GSC  │
   │(DataFor  │  │  MCP     │  │ MCP │   │ MCP  │
   │  SEO)    │  │(CF Worker│  │     │   │      │
   │          │  │   +      │  │     │   │      │
   │Keywords  │  │Container)│  │     │   │      │
   │Backlinks │  │          │  │     │   │      │
   │SERP      │  │          │  │     │   │      │
   │Lighthouse│  │          │  │     │   │      │
   └──────────┘  └────┬─────┘  └──┬──┘   └──┬───┘
                      │           │          │
                      ▼           ▼          ▼
              ┌──────────┐   Google      Google
              │Cloudflare│   Analytics   Search
              │Container │   4 API       Console
              │(Crawl4AI │               API
              │+Chromium)│
              └──────────┘
```

### Data Flow for a Full SEO Audit

```
1. User: "Audit example.com"

2. Claude orchestrates (in parallel where possible):
   ├── SEO-MCP → domain rank, ranked keywords, backlink profile
   ├── SEO-MCP → Lighthouse scores, content parsing
   ├── Crawler MCP → crawl all pages, extract content & structure
   ├── GA4 MCP → traffic trends, top pages, bounce rates
   └── GSC MCP → search queries, impressions, CTR, positions

3. Claude correlates ALL data:
   "Page /services lost 40% traffic (GA4) because position
    dropped from 3→8 for 'keyword' (GSC). Crawl shows the
    page has duplicate meta description and missing H1.
    Backlink profile shows 2 lost referring domains this month.
    Recommended fix: update content, fix H1, rebuild links."

4. Output: comprehensive strategy document with prioritized actions
```

---

## Build Plan — 5 Phases

### Phase 1: Site Crawler Container (Priority: HIGH)
**Time estimate: 1-2 weekends**
**Cost: $0 additional (uses existing $5/mo CF Workers plan)**

#### What to build
A Cloudflare Worker that acts as an MCP server and spins up a Cloudflare Container running Crawl4AI on demand to crawl websites.

#### Technical Requirements

**Container:**
- Docker image based on `unclecode/crawl4ai:0.8.0`
- Instance type: `standard-1` (1/2 vCPU, 4 GiB RAM, 8 GB disk)
- `sleepAfter: 120` seconds (auto-sleep when idle)
- Must have internet access enabled (`enableInternet: true`)
- Exposes HTTP API on port 8080

**Worker (MCP Server):**
- Cloudflare Worker with MCP SSE endpoint
- Routes to Container via Durable Object binding
- Handles MCP tool calls: `crawl_site`, `crawl_page`, `check_links`

**MCP Tools to expose:**

| Tool | Input | Output |
|------|-------|--------|
| `crawl_site` | URL, max_pages (default 100), max_depth (default 3) | Array of pages with: URL, status code, title, meta description, headings, internal links, external links, images (with alt text), canonical, word count, markdown content |
| `crawl_page` | URL | Single page deep analysis: full HTML + markdown content, all meta tags, structured data (JSON-LD), Open Graph tags, hreflang, canonical, response headers |
| `check_links` | URL or array of URLs | Status codes, redirect chains, broken links, response times |

**wrangler.jsonc config:**
```jsonc
{
  "name": "seo-crawler-mcp",
  "main": "src/index.ts",
  "containers": {
    "site_crawler": {
      "image": "./crawler",  // local Dockerfile or registry
      "instance_type": "standard-1",
      "max_instances": 3
    }
  },
  "durable_objects": {
    "bindings": [
      {
        "name": "SITE_CRAWLER",
        "class_name": "SiteCrawler"
      }
    ]
  }
}
```

**Container internal API (what Crawl4AI should expose on :8080):**
```
POST /crawl
Body: { "url": "https://example.com", "max_pages": 100, "max_depth": 3 }
Response: { "pages": [...], "summary": { "total_pages": 87, "broken_links": 3, ... } }

POST /page
Body: { "url": "https://example.com/about" }
Response: { full page analysis }

POST /links
Body: { "urls": ["https://example.com/page1", ...] }
Response: { status codes, redirects, broken links }
```

#### Files to create
```
seo-crawler-mcp/
├── src/
│   ├── index.ts          # Worker: MCP SSE endpoint + routing
│   ├── crawler.ts        # Container class (extends Container)
│   └── tools.ts          # MCP tool definitions
├── crawler/
│   ├── Dockerfile        # Based on crawl4ai, adds HTTP API
│   ├── api.py            # FastAPI/Flask wrapper around Crawl4AI
│   └── requirements.txt
├── wrangler.jsonc
├── package.json
└── tsconfig.json
```

#### Testing checklist
- [ ] Container boots and responds to health check within 5 seconds
- [ ] Crawl of 10-page site completes successfully
- [ ] Crawl of 100-page site completes within 15 minutes
- [ ] Container auto-sleeps after idle timeout
- [ ] MCP SSE endpoint connects from Claude.ai
- [ ] Tool calls work end-to-end: Claude → MCP → Worker → Container → results → Claude
- [ ] Broken links are detected and reported
- [ ] JavaScript-rendered pages are crawled correctly

#### Cost per crawl
| Site Size | Time | Estimated Cost |
|-----------|------|---------------|
| 20 pages | ~2 min | $0.002 |
| 100 pages | ~10 min | $0.009 |
| 500 pages | ~30 min | $0.027 |

~37 standard crawls/month included in $5 base plan.

---

### Phase 2: SEO Audit Logic Layer (Priority: HIGH)
**Time estimate: 1 weekend**
**Cost: $0 additional**

#### What to build
A middleware layer (inside the container or as a Worker post-processor) that runs SEO-specific checks on each crawled page. Based on logic from `seo-audit-mcp` (~500 lines TypeScript), adapted and extended.

#### SEO Checks to Implement

**Per-page checks:**
- [ ] Title tag: present, length (50-60 chars), uniqueness across site
- [ ] Meta description: present, length (150-160 chars), uniqueness
- [ ] H1: exactly one per page, contains target keyword
- [ ] Heading hierarchy: H1 → H2 → H3 (no skipped levels)
- [ ] Images: all have alt text, alt text is descriptive
- [ ] Internal links: count, anchor text diversity
- [ ] External links: count, nofollow usage, broken outbound links
- [ ] Canonical tag: present, self-referencing or pointing correctly
- [ ] Hreflang tags: present for multilingual sites, valid format
- [ ] Open Graph tags: og:title, og:description, og:image present
- [ ] Structured data (JSON-LD): valid, appropriate schema type
- [ ] Word count: flag thin content (<300 words)
- [ ] URL structure: length, use of keywords, special characters

**Site-wide checks:**
- [ ] Duplicate titles across pages
- [ ] Duplicate meta descriptions across pages
- [ ] Orphan pages (no internal links pointing to them)
- [ ] Internal link depth (pages >3 clicks from homepage)
- [ ] Redirect chains (>2 redirects)
- [ ] Mixed content (HTTP resources on HTTPS pages)
- [ ] Robots.txt analysis
- [ ] Sitemap.xml analysis (pages in sitemap vs. crawled pages)
- [ ] Internal link graph (which pages link where)

**Output format:**
```json
{
  "summary": {
    "pages_crawled": 87,
    "issues_critical": 3,
    "issues_warning": 12,
    "issues_info": 24,
    "score": 72
  },
  "critical": [
    { "type": "missing_h1", "pages": ["https://..."], "fix": "Add H1 tag" }
  ],
  "warnings": [...],
  "page_details": {
    "https://example.com/about": {
      "title": { "value": "About Us", "length": 8, "status": "warning", "note": "Too short" },
      "meta_description": { "value": null, "status": "critical", "note": "Missing" },
      ...
    }
  }
}
```

#### Source to adapt
Fork key logic from `RichardDillman/seo-audit-mcp`:
- Strip job-board specific code (JobPosting schema, job page classification)
- Add general business site checks (hreflang, canonical chains, Open Graph, link depth)
- Integrate as post-processing step after Crawl4AI returns page data

---

### Phase 3: Google Analytics 4 MCP (Priority: MEDIUM)
**Time estimate: 2-3 hours setup**
**Cost: Free**

#### What to install
`surendranb/google-analytics-mcp`

#### Prerequisites
1. Google Cloud project with GA4 Data API enabled
2. Service account created with GA4 property access
3. Service account JSON key file downloaded

#### Setup steps
```bash
# 1. Clone the repo
git clone https://github.com/surendranb/google-analytics-mcp.git
cd google-analytics-mcp

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Test credentials
python3 -c "
import os
from google.analytics.data_v1beta import BetaAnalyticsDataClient
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/path/to/service-account-key.json'
client = BetaAnalyticsDataClient()
print('✅ GA4 credentials working!')
"
```

#### Claude Desktop / Claude Code config
```json
{
  "mcpServers": {
    "ga4-analytics": {
      "command": "python3",
      "args": ["-m", "ga4_mcp_server"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service-account-key.json",
        "GA4_PROPERTY_ID": "123456789"
      }
    }
  }
}
```

#### Key capabilities
- 200+ GA4 dimensions and metrics
- Smart row estimation (prevents context window overflow)
- Auto-aggregation for large datasets
- Traffic sources, user behavior, conversion data
- Device/browser/geography breakdowns

#### Note on transport
Currently stdio only (runs locally). For remote access via claude.ai, would need to either:
- Run via Claude Desktop/Code (simplest)
- Wrap in Streamable HTTP endpoint on Cloudflare Worker (more complex, but enables claude.ai access)
- Use Stape's hosted GA4 MCP: `https://mcp-ga.stape.ai/mcp` (easiest remote option)

---

### Phase 4: Google Search Console MCP (Priority: MEDIUM)
**Time estimate: 1-2 hours setup (shares credentials with GA4)**
**Cost: Free**

#### What to install
**Option A (same developer as GA4):** `surendranb/google-search-console-mcp`
- Shares service account auth with GA4 setup
- Simpler, consistent interface

**Option B (more features):** `AminForou/mcp-gsc`
- 137 stars, 19 tools
- URL indexing submission
- OAuth support
- More community support

#### Recommended: Start with Option A (consistency with GA4), add Option B later if needed.

#### Setup steps (using same service account as GA4)
```bash
# 1. Clone the repo
git clone https://github.com/surendranb/google-search-console-mcp.git
cd google-search-console-mcp

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

#### Claude config (add alongside GA4)
```json
{
  "mcpServers": {
    "ga4-analytics": {
      "command": "python3",
      "args": ["-m", "ga4_mcp_server"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service-account-key.json",
        "GA4_PROPERTY_ID": "123456789"
      }
    },
    "gsc-search": {
      "command": "python3",
      "args": ["-m", "gsc_mcp_server"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service-account-key.json",
        "GSC_SITE_URL": "https://example.com/"
      }
    }
  }
}
```

#### Key capabilities
- Search queries with clicks, impressions, CTR, average position
- URL inspection (indexing status, crawl info)
- Sitemap management
- Device, country, search appearance breakdowns
- Date range comparisons

#### Google Cloud setup (shared with GA4)
One Google Cloud project handles both:
1. Enable **Google Analytics Data API**
2. Enable **Google Search Console API**
3. Create one service account
4. Add service account email to GA4 property (Viewer role)
5. Add service account email to GSC property (Full access)
6. Download one JSON key file — used by both MCP servers

---

### Phase 5: Google Business Profile (Priority: LOW)
**Time estimate: 30 minutes**
**Cost: Zapier free tier or $0 if using few actions**

#### What to use
Zapier MCP for Google Business Profile — already shown in search results. Enables:
- Create/manage GBP posts
- Reply to reviews
- Manage Q&A
- Raw HTTP requests to GBP API

#### Setup
Connect GBP through Zapier's MCP endpoint. Each MCP tool call uses 2 Zapier tasks from plan quota.

#### When to add
Only after Phases 1-4 are working. This is a nice-to-have for local SEO management, not critical for the core audit workflow.

---

## Complete Cost Stack (After All Phases)

| Component | Purpose | Monthly Cost |
|-----------|---------|-------------|
| Claude Pro | AI reasoning engine | ~$20 |
| SEO-MCP (DataForSEO) | Keywords, backlinks, SERP, Lighthouse | ~$5-20 |
| Cloudflare Workers Paid | MCP hosting + Container runtime | $5 |
| Crawl4AI | Site crawling engine | $0 (open source) |
| GA4 MCP | Traffic & behavior data | $0 |
| GSC MCP | Search performance data | $0 |
| Canva MCP | Visual content creation | $0 (already connected) |
| **Total** | **Full SEO platform** | **$30-45/mo** |

### What This Replaces

| Tool | Their Price | Equivalent Capability |
|------|-----------|----------------------|
| Ahrefs Standard | $249/mo | SEO-MCP covers keywords, backlinks, SERP |
| SEMrush Pro | $139.95/mo | SEO-MCP covers same + competitor analysis |
| Screaming Frog | $21.60/mo | Crawler Container covers full site crawling |
| GA4 (free but needs analyst) | $50-100/hr | GA4 MCP + Claude interprets automatically |
| SEO consultant analysis | $100-200/hr | Claude correlates all data sources |
| **Total replaced** | **$410+/mo** | |
| **Annual savings** | **~$4,500+** | |

---

## The Unique Value (What No One Else Can Do)

### Cross-Source Intelligence
No existing platform can answer this in one query:

> "Show me pages where GSC impressions are rising but clicks are flat,
> cross-reference with GA4 to check if those pages have high bounce rates,
> crawl them to check if meta descriptions are missing or duplicate,
> and pull keyword difficulty for the queries they're ranking for."

This touches 4 data sources, requires understanding relationships between them, and produces a strategic recommendation. Currently takes an SEO analyst half a day across four different tabs.

### The Closed-Loop Cycle

```
GSC data shows ranking drops
  → GA4 confirms traffic loss on those pages
    → Crawler identifies technical issues
      → SEO-MCP finds keyword opportunities to recover
        → Claude writes optimized content
          → Canva generates supporting visuals
            → GSC monitors recovery
              → Loop repeats
```

Every step informed by every other step, with an AI that holds the full context.

### Competitor Content Analysis
The crawler can crawl competitor sites too. Claude reads their actual page content, compares semantically with yours, and tells you specifically what topical depth you're missing. Ahrefs shows competitor keywords. This shows competitor content quality and gaps.

### Persistent Context
Claude's memory + cached data in SEO-MCP means it remembers previous audit findings. "What changed since our last audit?" becomes a real question. Traditional tools have historical data but not an AI that remembers the strategic context.

---

## Priority Order & Dependencies

```
Phase 1 ─── Site Crawler Container ──────────── HIGHEST PRIORITY
  │          (enables full site audits)          1-2 weekends
  │
  ├── Phase 2 ─── SEO Audit Logic ───────────── HIGH
  │               (adds automated checks)        1 weekend
  │               depends on: Phase 1
  │
  └── Phase 3+4 ── GA4 + GSC MCP ────────────── MEDIUM
                   (adds traffic/search data)    1 evening
                   independent of Phase 1
                   shares Google Cloud setup

Phase 5 ─── GBP via Zapier ──────────────────── LOW
             (local SEO management)              30 minutes
             independent of everything
```

Phases 3+4 can be done in parallel with Phase 1. The Google Cloud project setup is shared work that benefits both.

---

## Known Limitations & Mitigations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| Container cold start (2-3s) | Negligible — crawls take minutes anyway | Accept it |
| CF Containers beta status | Features may change, pricing may change | Google Cloud Run is backup with similar pricing |
| No persistent container storage | Crawl results lost after sleep | Store in Cloudflare R2 or KV |
| Chromium memory-hungry | Large sites may hit limits | Batch processing, close browser contexts between pages |
| GA4/GSC MCP are stdio (local) | Can't use from claude.ai directly | Use via Claude Desktop/Code, or wrap in remote endpoint |
| Crawl4AI is general-purpose | No built-in SEO scoring | Phase 2 adds SEO checks on top |
| DataForSEO API costs | Unpredictable if heavy usage | Cache aggressively, monitor spend |
| surendranb GSC MCP dormant since June 2025 | May not get updates | AminForou/mcp-gsc is actively maintained alternative |

---

## Definition of Done

The platform is complete when Claude can execute this workflow in a single conversation:

1. **"Audit example.com"** → crawls the site, runs SEO checks, pulls keyword data, checks Lighthouse → produces comprehensive technical audit

2. **"What's happening with our traffic?"** → pulls GA4 data for last 30 days, identifies trends, correlates with GSC query data → explains what's working and what's declining

3. **"Why did /services page drop in rankings?"** → checks GSC position history, GA4 traffic change, crawler for technical issues, backlink changes → pinpoints the cause

4. **"Create a content plan to recover"** → uses keyword research to find opportunities, writes content briefs, suggests internal linking structure → actionable plan

5. **"Write the blog post and create a social image"** → writes SEO-optimized content with target keywords, uses Canva MCP to generate matching visual → ready to publish
