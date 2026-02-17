# SEO Audit Infrastructure Setup

## Architecture

```
Claude (MCP tool)
    │
    ▼
CF Worker (API gateway + Bearer token auth + D1 writes)
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

**Security:** Every request to the Worker must include `Authorization: Bearer <token>`. The token is stored as a Cloudflare secret — it never appears in code or config files. Requests without a valid token get a 401 response.

---

## Step-by-Step Setup via Cloudflare Dashboard

### Step 1: Create a D1 Database

1. Log into [dash.cloudflare.com](https://dash.cloudflare.com)
2. In the left sidebar, go to **Workers & Pages** → **D1 SQL Database**
3. Click **Create database**
4. Name it `seo-audit-db`
5. Choose a location (or leave as automatic)
6. Click **Create**
7. **Copy the Database ID** from the overview page — you'll need it for `wrangler.toml`

### Step 2: Initialize the D1 Schema

1. On your D1 database page, click the **Console** tab
2. Open `infrastructure/d1-schema.sql` from this repo
3. Paste the entire SQL into the console
4. Click **Execute** (or run it in batches if the console limits statement count)
5. Verify the tables exist: run `SELECT name FROM sqlite_master WHERE type='table';`

You should see: `crawl_jobs`, `page_audits`, `site_issues`, `site_summaries`

### Step 3: Create an R2 Bucket

1. In the left sidebar, go to **R2 Object Storage**
2. Click **Create bucket**
3. Name it `seo-audit-snapshots`
4. Leave defaults (Standard storage class, automatic location)
5. Click **Create bucket**

### Step 4: Update wrangler.toml with your IDs

Open `infrastructure/worker/wrangler.toml` and fill in your D1 database ID:

```toml
[[d1_databases]]
binding = "DB"
database_name = "seo-audit-db"
database_id = "paste-your-database-id-here"
```

### Step 5: Generate an API Key (Bearer Token)

Generate a strong random token. This is the shared secret between the MCP tool and the Worker:

```bash
# Option A: openssl
openssl rand -hex 32

# Option B: python
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Save this token** — you'll set it as a secret in Step 6 and use it in the MCP config in Step 8.

### Step 6: Deploy the Worker + Container

```bash
# Install wrangler v4+ (if not already installed)
npm install -g wrangler

# Login to your Cloudflare account
wrangler login

# Install worker dependencies
cd infrastructure/worker
npm install

# Deploy — this builds the Docker image, pushes it to CF registry,
# and deploys the Worker with Container binding
npm run deploy
```

**Requirements:**
- Docker must be running locally (wrangler builds the image with Docker)
- First deploy takes several minutes (image build + push + container provisioning)
- After the first deploy, wait ~3-5 minutes before the container is ready

### Step 7: Set the API Key Secret

After deployment, set your Bearer token as an encrypted secret:

**Option A: CLI (recommended)**
```bash
wrangler secret put API_KEY
# Paste your token from Step 5 when prompted
```

**Option B: Dashboard**
1. Go to **Workers & Pages** in the sidebar
2. Click on **seo-audit-gateway**
3. Go to **Settings** → **Variables and Secrets**
4. Under **Secrets**, click **Add**
5. Name: `API_KEY`
6. Value: paste your token from Step 5
7. Click **Save and deploy**

### Step 8: Verify the Deployment

Test that auth works:

```bash
# Should return 401 Unauthorized
curl https://seo-audit-gateway.<your-subdomain>.workers.dev/jobs

# Should return {"jobs": []}
curl -H "Authorization: Bearer <your-token>" \
  https://seo-audit-gateway.<your-subdomain>.workers.dev/jobs
```

Your Worker URL is shown in the Cloudflare dashboard under **Workers & Pages** → **seo-audit-gateway** → **Overview**.

### Step 9: Configure the MCP Tool for Claude

Add to your Claude Code MCP config (`~/.claude/mcp.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "seo-audit": {
      "command": "node",
      "args": ["/absolute/path/to/infrastructure/mcp-db-tool/index.js"],
      "env": {
        "GATEWAY_URL": "https://seo-audit-gateway.<your-subdomain>.workers.dev",
        "API_KEY": "<your-token-from-step-5>"
      }
    }
  }
}
```

Install MCP tool dependencies:
```bash
cd infrastructure/mcp-db-tool
npm install
```

---

## Security: How Token Auth Works

The Worker checks every incoming request for a valid Bearer token:

```
Authorization: Bearer <token>
```

- The token is stored as a **Cloudflare Secret** (`API_KEY`) — encrypted at rest, never visible in dashboard after creation, not in source code
- The MCP tool sends this token with every request via the `API_KEY` env var
- Requests without a valid token receive `401 Unauthorized`
- The Container is **not directly accessible** from the internet — it only receives requests proxied through the Worker's Durable Object binding
- D1 and R2 are also not publicly accessible — only the Worker can read/write them

**To rotate the token:**
1. Generate a new token: `openssl rand -hex 32`
2. Update the secret: `wrangler secret put API_KEY` (paste new token)
3. Update your MCP config with the new token
4. Restart Claude Code to pick up the new MCP config

---

## Managing via Dashboard After Deploy

### View Worker Logs
1. **Workers & Pages** → **seo-audit-gateway** → **Logs** → **Real-time logs**
2. Open a new tab and send a request — you'll see it stream in
3. Container lifecycle events (`onStart`, `onStop`, `onError`) appear here too

### View Container Status
1. **Workers & Pages** → **seo-audit-gateway** → **Containers** tab
2. Shows active instances, resource usage, and container logs

### Query D1 Data
1. **Workers & Pages** → **D1 SQL Database** → **seo-audit-db**
2. Click **Console** tab
3. Run queries like:
   ```sql
   SELECT id, domain, status, score FROM crawl_jobs ORDER BY created_at DESC LIMIT 10;
   ```

### Browse R2 Snapshots
1. **R2 Object Storage** → **seo-audit-snapshots**
2. Files are stored as `<job-id>/<encoded-url>.html`

### Update Environment Variables
1. **Workers & Pages** → **seo-audit-gateway** → **Settings** → **Variables and Secrets**
2. **Variables** (plain text): `ENVIRONMENT`, `MAX_PAGES_DEFAULT`, `MAX_DEPTH_DEFAULT`
3. **Secrets** (encrypted): `API_KEY`

---

## Usage Flow

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
5. Claude uses `query_db` for deeper analysis

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
- **Instance type:** `standard-1` (needs CPU + memory for headless browser)
- **Sleep timeout:** 5 minutes idle → container sleeps (saves cost)
- **Max instances:** 10 concurrent crawl jobs

### Container endpoints (internal, called by Worker only):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/start` | POST | Begin a crawl (returns 202, runs in background) |
| `/status` | GET | Progress + results when done |
| `/health` | GET | Liveness check |

These endpoints are **not accessible from the internet**. Only the Worker's Durable Object can reach them via the internal container binding.
