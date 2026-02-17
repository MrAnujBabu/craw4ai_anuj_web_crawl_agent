# SEO Audit Infrastructure Setup

## Architecture

```
Claude (MCP client)
    │
    ├──→ MCP over HTTP ──→ CF Worker (SEOAuditMcpAgent DO)
    │                          │
    │                          ├──→ Cloudflare D1  (structured audit data)
    │                          ├──→ Cloudflare R2  (raw HTML snapshots)
    │                          └──→ CF Container   (crawl4ai + SEO audit)
    │                                    │
    │                                    ▼
    │                               Python HTTP server on port 8000
    │                               running crawl4ai + SEOAnalyzer
    │
    └──→ (alt) MCP stdio ──→ mcp-db-tool ──REST──→ CF Worker
```

**Key design:** The Worker is both an MCP server (via Cloudflare Agents SDK) and a REST API gateway. Claude connects directly via MCP — no local process needed. Each crawl job gets its own Container instance (Durable Object keyed by job_id).

**Auth:** Token in URL path for MCP (`/mcp/<token>`), Bearer header for REST API. Token stored as Cloudflare secret.

---

## Step-by-Step Setup

### Step 1: Create a D1 Database

1. Log into [dash.cloudflare.com](https://dash.cloudflare.com)
2. Go to **Workers & Pages** → **D1 SQL Database**
3. Click **Create database**, name it `seo-audit-db`
4. **Copy the Database ID** — you'll need it for `wrangler.toml`

### Step 2: Initialize the D1 Schema

1. On your D1 database page, click **Console**
2. Paste the contents of `infrastructure/d1-schema.sql`
3. Click **Execute**
4. Verify: `SELECT name FROM sqlite_master WHERE type='table';`

You should see: `crawl_jobs`, `page_audits`, `site_issues`, `site_summaries`

### Step 3: Create an R2 Bucket

1. Go to **R2 Object Storage**
2. Click **Create bucket**, name it `seo-audit-snapshots`
3. Leave defaults

### Step 4: Update wrangler.toml

Open `infrastructure/worker/wrangler.toml` and fill in your D1 database ID:

```toml
[[d1_databases]]
binding = "DB"
database_name = "seo-audit-db"
database_id = "paste-your-database-id-here"
```

### Step 5: Generate an API Key

```bash
openssl rand -hex 32
```

Save this token — it's the shared secret for both MCP and REST auth.

### Step 6: Deploy

```bash
cd infrastructure
./deploy.sh
```

This script:
1. Copies `crawl4ai/` source into the Docker build context
2. Installs Worker dependencies
3. Deploys the Worker + Container to Cloudflare

**Requirements:**
- Docker running locally (wrangler builds the container image)
- `wrangler login` completed
- First deploy takes several minutes (image build + push)

### Step 7: Set the API Key Secret

```bash
cd infrastructure/worker
wrangler secret put API_KEY
# Paste your token when prompted
```

Or via Dashboard: **Workers & Pages** → **seo-audit-gateway** → **Settings** → **Variables and Secrets** → Add secret `API_KEY`.

### Step 8: Verify

```bash
# Health check (no auth required)
curl https://seo-audit-gateway.<your-subdomain>.workers.dev/health

# REST API (should return {"jobs": []})
curl -H "Authorization: Bearer <your-token>" \
  https://seo-audit-gateway.<your-subdomain>.workers.dev/jobs

# MCP without token (should return 403)
curl https://seo-audit-gateway.<your-subdomain>.workers.dev/mcp

# MCP with bad token (should return 403)
curl -X POST https://seo-audit-gateway.<your-subdomain>.workers.dev/mcp/bad-token
```

---

## Connecting Claude

### Option A: Direct MCP (Recommended)

No local setup needed. Add to your MCP config (`~/.claude/mcp.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "seo-audit": {
      "type": "url",
      "url": "https://seo-audit-gateway.<your-subdomain>.workers.dev/mcp/<your-token>"
    }
  }
}
```

This uses the same pattern as the DataForSEO MCP server — token in URL path, MCP over streamable HTTP.

### Option B: SSE Transport

If your MCP client only supports SSE:

```json
{
  "mcpServers": {
    "seo-audit": {
      "type": "url",
      "url": "https://seo-audit-gateway.<your-subdomain>.workers.dev/sse/<your-token>"
    }
  }
}
```

### Option C: Stdio Fallback (Claude Desktop / Claude Code)

For local stdio transport:

```bash
cd infrastructure/mcp-db-tool
npm install
```

```json
{
  "mcpServers": {
    "seo-audit": {
      "command": "node",
      "args": ["/absolute/path/to/infrastructure/mcp-db-tool/index.js"],
      "env": {
        "GATEWAY_URL": "https://seo-audit-gateway.<your-subdomain>.workers.dev",
        "API_KEY": "<your-token>"
      }
    }
  }
}
```

---

## Security

### Token Auth
- **MCP routes:** Token in URL path (`/mcp/<token>`, `/sse/<token>`)
- **REST routes:** Bearer token in header (`Authorization: Bearer <token>`)
- **Storage:** Cloudflare Secret (encrypted at rest, never visible after creation)
- **Container:** Not directly accessible from internet — only via Worker DO binding
- **D1/R2:** Not publicly accessible — Worker only

### Rotating the Token
1. Generate new token: `openssl rand -hex 32`
2. Update secret: `wrangler secret put API_KEY`
3. Update your MCP config URL with the new token
4. Restart Claude to pick up the new config

---

## Available Tools

| Tool | Description |
|------|-------------|
| `submit_crawl` | Start a crawl — spins up a CF Container |
| `poll_job` | Poll live progress from the running container |
| `list_jobs` | List jobs by domain/status |
| `get_job` | Get job summary + SEO score |
| `get_issues` | Get all SEO issues (filterable by severity) |
| `get_pages` | Get page-level audit details |
| `query_db` | Run custom SQL against D1 |

### Example Conversation

> **You:** "Run an SEO audit on example.com"

1. Claude uses `submit_crawl(url="https://example.com")` → gets job_id
2. Claude uses `poll_job(job_id)` → sees "running, 12/50 pages"
3. Claude uses `poll_job(job_id)` → sees "completed, score 73/100"
4. Claude uses `get_issues(job_id, severity="critical")` → reports findings
5. Claude uses `get_pages(job_id, problems_only=true)` → shows problem pages
6. Claude uses `query_db` for deeper analysis

---

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
- **Instance type:** `standard-1` (CPU + memory for headless browser)
- **Sleep timeout:** 5 minutes idle → container sleeps (saves cost)
- **Max instances:** 10 concurrent crawl jobs

### Container Endpoints (internal, Worker-only):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/start` | POST | Begin a crawl (returns 202, runs in background) |
| `/status` | GET | Progress + results when done |
| `/health` | GET | Liveness check |

---

## Dashboard Management

### View Worker Logs
**Workers & Pages** → **seo-audit-gateway** → **Logs** → **Real-time logs**

### View Container Status
**Workers & Pages** → **seo-audit-gateway** → **Containers** tab

### Query D1 Data
**D1 SQL Database** → **seo-audit-db** → **Console**

### Browse R2 Snapshots
**R2 Object Storage** → **seo-audit-snapshots** (files stored as `<job-id>/<encoded-url>.html`)

### Update Secrets
**Workers & Pages** → **seo-audit-gateway** → **Settings** → **Variables and Secrets**
