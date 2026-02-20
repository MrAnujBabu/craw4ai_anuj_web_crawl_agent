#!/usr/bin/env bash
set -euo pipefail

# ─── SEO Audit Infrastructure Deploy Script ──────────────────────────
#
# This script:
#   1. Copies the crawl4ai source (with seo_audit) into the Docker build context
#   2. Installs Worker dependencies
#   3. Deploys the Worker + Container to Cloudflare
#
# Prerequisites:
#   - Docker running locally
#   - wrangler logged in (wrangler login)
#   - D1 database created and ID filled in wrangler.toml
#   - API_KEY secret set (wrangler secret put API_KEY)
#
# Usage:
#   cd infrastructure
#   ./deploy.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== SEO Audit Infrastructure Deploy ==="
echo ""

# 1. Stage crawl4ai source into Docker build context
echo "[1/3] Staging crawl4ai source into Docker build context..."
rm -rf "$SCRIPT_DIR/docker/crawl4ai"
cp -r "$REPO_ROOT/crawl4ai" "$SCRIPT_DIR/docker/crawl4ai"
echo "  Copied crawl4ai/ → infrastructure/docker/crawl4ai/"

# 2. Install Worker dependencies
echo "[2/3] Installing Worker dependencies..."
cd "$SCRIPT_DIR/worker"
npm install

# 3. Deploy
echo "[3/3] Deploying Worker + Container to Cloudflare..."
npm run deploy

echo ""
echo "=== Deploy complete ==="
echo ""
echo "Your Worker URL is shown above. To connect Claude via MCP:"
echo "  URL: https://seo-audit-gateway.<your-subdomain>.workers.dev/mcp/<your-api-key>"
echo ""
echo "Or for SSE transport:"
echo "  URL: https://seo-audit-gateway.<your-subdomain>.workers.dev/sse/<your-api-key>"

# Clean up staged source
rm -rf "$SCRIPT_DIR/docker/crawl4ai"
echo ""
echo "Cleaned up staged crawl4ai source."
