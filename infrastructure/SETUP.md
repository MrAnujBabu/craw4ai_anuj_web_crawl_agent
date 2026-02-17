# SEO Audit Infrastructure Setup

## Architecture

```
Claude (MCP tool) ──→ CF Worker Gateway ──→ Docker Container (crawl4ai)
                            │                        │
                            ▼                        ▼
                       Cloudflare D1 ◄───── results written
                       (+ R2 for HTML)
```

## 1. Create Cloudflare Resources

```bash
# Install wrangler
npm install -g wrangler

# Login
wrangler login

# Create D1 database
wrangler d1 create seo-audit-db
# Copy the database_id into infrastructure/worker/wrangler.toml

# Create R2 bucket
wrangler r2 bucket create seo-audit-snapshots

# Initialize the schema
cd infrastructure/worker
npm run db:init

# Set secrets
wrangler secret put API_KEY          # your chosen bearer token
wrangler secret put DOCKER_API_URL   # URL that triggers Docker containers
```

## 2. Deploy the Worker

```bash
cd infrastructure/worker
npm install
npm run deploy
```

Your gateway will be live at `https://seo-audit-gateway.<your-subdomain>.workers.dev`.

## 3. Build the Docker Image

```bash
# From repo root
docker build -f infrastructure/docker/Dockerfile -t seo-audit-crawler .
```

Run it (locally or via your container orchestrator):

```bash
docker run --rm \
  -e JOB_ID="test-job-id" \
  -e START_URL="https://example.com" \
  -e CALLBACK_URL="https://seo-audit-gateway.you.workers.dev/jobs/test-job-id/results" \
  -e API_KEY="your-api-key" \
  -e MAX_PAGES=50 \
  -e MAX_DEPTH=3 \
  seo-audit-crawler
```

## 4. Docker Orchestration

The Worker needs a `DOCKER_API_URL` — something that accepts a POST and spins up a container. Options:

- **Cloudflare Workers + Containers** (if available in your plan)
- **Railway / Fly.io / Render** — deploy the Docker image as an on-demand service
- **Self-hosted** — a small HTTP server that does `docker run` on request
- **AWS ECS / GCP Cloud Run** — serverless container execution

The Worker POSTs this payload to `DOCKER_API_URL`:
```json
{
  "job_id": "uuid",
  "url": "https://example.com",
  "config": { "max_pages": 50, "max_depth": 3 },
  "callback_url": "https://gateway/jobs/{id}/results"
}
```

## 5. Set Up the MCP Tool for Claude

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

## 6. Usage Flow (as Claude)

Once configured, Claude has 5 tools:

```
submit_crawl    → Start a crawl: "Audit https://example.com"
list_jobs       → Check status:  "List running jobs"
get_job         → Get summary:   "Show results for job abc123"
get_issues      → See problems:  "What are the critical issues?"
query_db        → Custom SQL:    "Find all pages missing H1 tags"
```

### Example workflow:

1. **You:** "Run an SEO audit on example.com"
2. **Claude:** uses `submit_crawl` → gets job_id
3. **Claude:** uses `get_job` to poll until status = completed
4. **Claude:** uses `get_issues` with severity=critical → reports findings
5. **Claude:** uses `query_db` for deeper analysis:
   ```sql
   SELECT url, title, h1_count, word_count
   FROM page_audits
   WHERE job_id = 'xxx' AND word_count < 300
   ORDER BY word_count
   ```

## DB Schema Reference

| Table | Purpose |
|-------|---------|
| `crawl_jobs` | Job lifecycle tracking |
| `page_audits` | Per-page SEO results (key fields + full JSON) |
| `site_issues` | Flat issue list (type, severity, affected URLs) |
| `site_summaries` | Site-wide score and aggregate stats |

| View | Purpose |
|------|---------|
| `v_latest_audits` | Most recent audit per domain |
| `v_critical_issues` | All critical issues across domains |
| `v_problem_pages` | Pages with any SEO failure |

Full schema: `infrastructure/d1-schema.sql`
