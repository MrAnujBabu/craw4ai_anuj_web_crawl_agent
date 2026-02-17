"""
Container HTTP server for Cloudflare Containers.

The CF Worker proxies requests via container.fetch() to this server.
Runs on port 8000 (matching CrawlerContainer.defaultPort).

Endpoints:
    POST /start   — Begin a crawl job (returns immediately, runs in background)
    GET  /status   — Poll crawl progress and retrieve results when done
    GET  /health   — Liveness check
"""

import sys
import json
import asyncio
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, "/app")

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.seo_audit import SEOAnalyzer

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("seo-container")

# ─── Shared State ─────────────────────────────────────────────────────
# One crawl per container instance (one container per job)

state = {
    "status": "idle",       # idle | running | completed | failed
    "job_id": None,
    "pages_found": 0,
    "pages_done": 0,
    "error": None,
    "results": None,        # set when completed
}
state_lock = threading.Lock()


# ─── Crawl Runner (async, runs in background thread) ─────────────────

def run_crawl_in_thread(job_id: str, url: str, max_pages: int, max_depth: int):
    """Runs the async crawl in a new event loop on a background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_crawl(job_id, url, max_pages, max_depth))
    except Exception as e:
        logger.error(f"Crawl thread failed: {e}", exc_info=True)
        with state_lock:
            state["status"] = "failed"
            state["error"] = str(e)
    finally:
        loop.close()


async def _crawl(job_id: str, url: str, max_pages: int, max_depth: int):
    logger.info(f"Starting crawl: job={job_id} url={url} max_pages={max_pages}")

    analyzer = SEOAnalyzer()

    crawl_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        deep_crawl_strategy=BFSDeepCrawlStrategy(
            max_depth=max_depth,
            max_pages=max_pages,
        ),
    )

    async with AsyncWebCrawler() as crawler:
        results = await crawler.arun(url=url, config=crawl_config)
        crawl_results = results if isinstance(results, list) else [results]

    with state_lock:
        state["pages_found"] = len(crawl_results)

    logger.info(f"Crawled {len(crawl_results)} pages, running SEO audit")

    # Run SEO audit
    site_result = analyzer.analyze_site(crawl_results)
    logger.info(f"Audit done. Score: {site_result.summary.score}/100")

    # Build result payload (same shape the Worker expects)
    pages_payload = []
    snapshots_payload = []

    for url_key, page_audit in site_result.page_details.items():
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

    for cr in crawl_results:
        if cr.success and cr.html:
            snapshots_payload.append({
                "url": cr.url,
                "html": cr.html[:500_000],
            })

    issues_payload = []
    for issue in site_result.critical + site_result.warnings + site_result.info:
        issues_payload.append({
            "issue_type": issue.issue_type,
            "severity": issue.severity.value,
            "description": issue.description,
            "fix": issue.fix,
            "affected_count": len(issue.affected_pages),
            "affected_urls": issue.affected_pages[:50],
        })

    summary_dict = site_result.summary.model_dump()
    summary_payload = {
        "pages_audited": summary_dict["pages_audited"],
        "score": summary_dict["score"],
        "issues_critical": summary_dict["issues_critical"],
        "issues_warning": summary_dict["issues_warning"],
        "issues_info": summary_dict["issues_info"],
        "audit_json": json.dumps(summary_dict),
    }

    with state_lock:
        state["status"] = "completed"
        state["pages_done"] = len(pages_payload)
        state["results"] = {
            "pages": pages_payload,
            "issues": issues_payload,
            "summary": summary_payload,
            "snapshots": snapshots_payload,
        }

    logger.info(f"Results ready: {len(pages_payload)} pages, {len(issues_payload)} issues")


# ─── HTTP Request Handler ─────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok"})

        elif self.path == "/status":
            with state_lock:
                resp = {
                    "status": state["status"],
                    "job_id": state["job_id"],
                    "pages_found": state["pages_found"],
                    "pages_done": state["pages_done"],
                    "error": state["error"],
                }
                # Include full results when completed (Worker ingests them)
                if state["status"] == "completed":
                    resp["results"] = state["results"]
            self._respond(200, resp)

        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/start":
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length)) if content_length else {}

            with state_lock:
                if state["status"] == "running":
                    self._respond(409, {"error": "crawl already running"})
                    return

                state["status"] = "running"
                state["job_id"] = body.get("job_id")
                state["pages_found"] = 0
                state["pages_done"] = 0
                state["error"] = None
                state["results"] = None

            # Start crawl in background thread
            t = threading.Thread(
                target=run_crawl_in_thread,
                args=(
                    body.get("job_id", ""),
                    body["url"],
                    body.get("max_pages", 50),
                    body.get("max_depth", 3),
                ),
                daemon=True,
            )
            t.start()

            self._respond(202, {"status": "started", "job_id": body.get("job_id")})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        # Suppress default access logs, use our logger instead
        logger.debug(f"{self.address_string()} {format % args}")


# ─── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 8000
    server = HTTPServer(("0.0.0.0", port), Handler)
    logger.info(f"SEO audit container listening on port {port}")
    server.serve_forever()
