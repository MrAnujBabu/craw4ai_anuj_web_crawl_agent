# SEO Audit Infrastructure Setup

## Architecture

```
Claude (MCP tool)
    │
    ▼
CF Worker (API gateway + auth + D1 writes)
    │
    ├──→ Cloudflare D1  (structured audit data)
    ├──→ Cloudflare R2  (raw HTML snapshots)
    └──→ CF Container   (crawl4ai + SEO audit, one per job)
              │
              ▼
         Python HTTP server on port 8000
         running crawl4ai + SEOAnalyzer
```

**Key design:** Each crawl job gets its own Container instance (Durable Object keyed by job_id). The Worker is the only thing that talks to D1. The container runs the crawl and exposes results via HTTP; the Worker polls `/status` and ingests results when done.

## 1. Create Cloudflare Resources

```bash
# Install wrangler v4+
npm install -g wrangler

# Login
wrangler login

# Create D1 database
wrangler d1 create seo-audit-db
# → Copy the database_id into infrastructure/worker/wrangler.toml

# Create R2 bucket
wrangler r2 bucket create seo-audit-snapshots

# Initialize the D1 schema
cd infrastructure/worker
npm install
npm run db:init

# Set API key secret
wrangler secret put API_KEY
```

## 2. Deploy (Worker + Container)

```bash
cd infrastructure/worker
npm run deploy
```

This single command:
1. Builds the Docker image from `infrastructure/docker/` (requires Docker running locally)
2. Pushes it to Cloudflare's container registry
3. Deploys the Worker with the Container binding

First deploy takes a few minutes (image build + push). Subsequent deploys are faster due to layer caching.

**Important:** After the first deploy, wait a few minutes for container provisioning before sending requests.

## 3. Set Up the MCP Tool for Claude

Add to your Claude Code MCP config (`~/.claude/mcp.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "seo-audit": {
      "command": "node",
      "args": ["/absolute/path/to/infrastructure/mcp-db-tool/index.js"],
      "env": {
        "GATEWAY_URL": "https://seo-audit-gateway.your-subdomain.workers.dev",
        "API_KEY": "your-api-key"
      }
    }
  }
}
```

Then install deps:
```bash
cd infrastructure/mcp-db-tool
npm install
```

## 4. Usage Flow

Once configured, Claude has 6 tools:

| Tool | Purpose |
|------|---------|
| `submit_crawl` | Start a crawl — spins up a CF Container |
| `poll_job` | Poll live progress from the running container |
| `list_jobs` | List jobs by domain/status |
| `get_job` | Get job summary + SEO score |
| `get_issues` | Get all SEO issues (filterable by severity) |
| `query_db` | Run custom SQL against D1 |

### Example conversation:

> **You:** "Run an SEO audit on example.com"

1. Claude uses `submit_crawl(url="https://example.com")` → gets job_id
2. Claude uses `poll_job(job_id)` → sees "running, 12/50 pages"
3. Claude uses `poll_job(job_id)` → sees "completed, score 73/100"
4. Claude uses `get_issues(job_id, severity="critical")` → reports findings
5. Claude uses `query_db` for deeper analysis:
   ```sql
   SELECT url, title, h1_count, word_count
   FROM page_audits
   WHERE job_id = 'xxx' AND title_status = 'fail'
   ORDER BY word_count
   ```

## DB Schema Reference

| Table | Purpose |
|-------|---------|
| `crawl_jobs` | Job lifecycle (status, domain, score, timestamps) |
| `page_audits` | Per-page SEO metrics + full JSON audit result |
| `site_issues` | Flat issue list (type, severity, affected URLs, fix) |
| `site_summaries` | Site-wide score and aggregate stats |

| View | Purpose |
|------|---------|
| `v_latest_audits` | Most recent completed audit per domain |
| `v_critical_issues` | All critical issues across all domains |
| `v_problem_pages` | Pages with any SEO failure |

Full schema: `infrastructure/d1-schema.sql`

## Container Details

- **Image:** Built from `infrastructure/docker/Dockerfile`
- **Runtime:** Python 3.11 + Chromium (via Playwright)
- **Port:** 8000 (HTTP server)
- **Instance type:** `standard-1` (needs CPU + memory for headless browser)
- **Sleep timeout:** 30 minutes idle → container sleeps (saves cost)
- **Max instances:** 10 concurrent crawl jobs

### Container endpoints (internal, called by Worker):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/start` | POST | Begin a crawl (returns 202, runs in background) |
| `/status` | GET | Progress + results when done |
| `/health` | GET | Liveness check |
