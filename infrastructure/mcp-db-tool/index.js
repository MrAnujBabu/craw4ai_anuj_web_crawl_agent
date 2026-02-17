/**
 * SEO Audit MCP Tool — Stdio fallback for Claude Code / Claude Desktop.
 *
 * Connects to the Cloudflare Worker gateway and exposes 7 tools:
 *   1. submit_crawl    — Start a new SEO audit crawl (spins up CF Container)
 *   2. poll_job        — Poll live crawl progress from the container
 *   3. list_jobs       — List crawl jobs (filter by domain/status)
 *   4. get_job         — Get job details + audit summary
 *   5. get_issues      — Get SEO issues for a job
 *   6. get_pages       — Get page-level audit details
 *   7. query_db        — Run arbitrary read-only SQL against D1
 *
 * Configuration (env vars):
 *   GATEWAY_URL  — Base URL of the CF Worker (e.g. https://seo-audit-gateway.you.workers.dev)
 *   API_KEY      — Bearer token for the Worker
 *
 * NOTE: For direct MCP connection (no stdio process needed), use the Worker's
 * MCP endpoint instead: https://seo-audit-gateway.<subdomain>.workers.dev/mcp/<token>
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const GATEWAY_URL = process.env.GATEWAY_URL || "http://localhost:8787";
const API_KEY = process.env.API_KEY || "";

// ─── Gateway Client ──────────────────────────────────────────────────

async function gateway(method, path, body) {
  const url = `${GATEWAY_URL}${path}`;
  const opts = {
    method,
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      "Content-Type": "application/json",
    },
  };
  if (body) opts.body = JSON.stringify(body);

  const resp = await fetch(url, opts);
  const data = await resp.json();

  if (!resp.ok) {
    throw new Error(data.error || `Gateway returned ${resp.status}`);
  }
  return data;
}

// ─── MCP Server ──────────────────────────────────────────────────────

const server = new McpServer(
  { name: "seo-audit-db", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

// ── submit_crawl ─────────────────────────────────────────────────────
server.tool(
  "submit_crawl",
  "Start a new SEO audit crawl for a website. Returns a job_id you can use to check status and retrieve results.",
  {
    url: z.string().describe("The starting URL to crawl (e.g. https://example.com)"),
    max_pages: z.number().optional().describe("Maximum pages to crawl (default: 50)"),
    max_depth: z.number().optional().describe("Maximum crawl depth from start URL (default: 3)"),
  },
  async ({ url, max_pages, max_depth }) => {
    const result = await gateway("POST", "/crawl", { url, max_pages, max_depth });
    return {
      content: [{
        type: "text",
        text: `Crawl job submitted. A Cloudflare Container is spinning up.\n\nJob ID: ${result.job_id}\nDomain: ${result.domain}\nStatus: ${result.status}\n\nUse poll_job to check progress. Once completed, use get_issues to see findings.`,
      }],
    };
  }
);

// ── poll_job ─────────────────────────────────────────────────────────
server.tool(
  "poll_job",
  "Poll the live status of a running crawl job. If completed, the Worker automatically ingests results into D1.",
  {
    job_id: z.string().describe("The job UUID from submit_crawl"),
  },
  async ({ job_id }) => {
    const result = await gateway("GET", `/jobs/${job_id}/status`);
    let out = `Job: ${result.id}\nStatus: ${result.status}`;
    if (result.pages_done !== undefined) out += `\nPages crawled: ${result.pages_done}`;
    if (result.pages_found !== undefined) out += `\nPages found: ${result.pages_found}`;
    if (result.score !== undefined && result.score !== null) out += `\nSEO Score: ${result.score}/100`;
    if (result.error) out += `\nError: ${result.error}`;
    if (result.status === "completed") {
      out += `\n\nCrawl complete! Use get_job for summary, get_issues for problems, or query_db for custom analysis.`;
    } else if (result.status === "running") {
      out += `\n\nStill running. Poll again in a few seconds.`;
    }
    return { content: [{ type: "text", text: out }] };
  }
);

// ── list_jobs ────────────────────────────────────────────────────────
server.tool(
  "list_jobs",
  "List SEO audit jobs. Filter by domain and/or status (queued, running, completed, failed).",
  {
    domain: z.string().optional().describe("Filter by domain (e.g. example.com)"),
    status: z.enum(["queued", "running", "completed", "failed"]).optional().describe("Filter by job status"),
    limit: z.number().optional().describe("Max results to return (default: 20, max: 100)"),
  },
  async ({ domain, status, limit }) => {
    const params = new URLSearchParams();
    if (domain) params.set("domain", domain);
    if (status) params.set("status", status);
    if (limit) params.set("limit", String(limit));

    const result = await gateway("GET", `/jobs?${params}`);
    if (!result.jobs?.length) return { content: [{ type: "text", text: "No jobs found matching your criteria." }] };

    const lines = result.jobs.map(
      (j) => `- ${j.id} | ${j.domain} | ${j.status} | score: ${j.score ?? "—"} | ${j.pages_done ?? 0} pages | ${j.created_at}`
    );
    return { content: [{ type: "text", text: `Found ${result.jobs.length} job(s):\n\n${lines.join("\n")}` }] };
  }
);

// ── get_job ──────────────────────────────────────────────────────────
server.tool(
  "get_job",
  "Get full details for a specific audit job, including the site-wide summary with SEO score, issue counts, and page stats.",
  {
    job_id: z.string().describe("The job UUID"),
  },
  async ({ job_id }) => {
    const result = await gateway("GET", `/jobs/${job_id}`);
    const j = result.job;
    let out = `Job: ${j.id}\nDomain: ${j.domain}\nURL: ${j.start_url}\nStatus: ${j.status}`;
    out += `\nCreated: ${j.created_at}`;
    if (j.completed_at) out += `\nCompleted: ${j.completed_at}`;
    if (j.error) out += `\nError: ${j.error}`;

    if (result.summary) {
      const s = result.summary;
      out += `\n\n── Site Audit Summary ──`;
      out += `\nSEO Score: ${s.score}/100`;
      out += `\nPages Audited: ${s.pages_audited}`;
      out += `\nCritical Issues: ${s.issues_critical}`;
      out += `\nWarnings: ${s.issues_warning}`;
      out += `\nInfo: ${s.issues_info}`;
    }
    return { content: [{ type: "text", text: out }] };
  }
);

// ── get_issues ───────────────────────────────────────────────────────
server.tool(
  "get_issues",
  "Get all SEO issues found for a crawl job. Filter by severity. Returns issue type, description, fix, and affected URLs.",
  {
    job_id: z.string().describe("The job UUID"),
    severity: z.enum(["critical", "warning", "info"]).optional().describe("Filter by severity level"),
  },
  async ({ job_id, severity }) => {
    const params = new URLSearchParams();
    if (severity) params.set("severity", severity);

    const result = await gateway("GET", `/jobs/${job_id}/issues?${params}`);
    if (!result.issues?.length) return { content: [{ type: "text", text: "No issues found." }] };

    const lines = result.issues.map((i) => {
      const urls = i.affected_urls ? JSON.parse(i.affected_urls).slice(0, 5) : [];
      let line = `[${i.severity.toUpperCase()}] ${i.issue_type}: ${i.description}`;
      if (i.fix) line += `\n  Fix: ${i.fix}`;
      if (urls.length)
        line += `\n  Affected: ${urls.join(", ")}${i.affected_count > 5 ? ` (+${i.affected_count - 5} more)` : ""}`;
      return line;
    });

    return { content: [{ type: "text", text: `Found ${result.issues.length} issue(s):\n\n${lines.join("\n\n")}` }] };
  }
);

// ── get_pages ────────────────────────────────────────────────────────
server.tool(
  "get_pages",
  "Get page-level audit details for a crawl job. Can filter to only pages with SEO problems.",
  {
    job_id: z.string().describe("The job UUID"),
    problems_only: z.boolean().optional().describe("Only return pages with SEO problems (default: false)"),
    limit: z.number().optional().describe("Max results (default: 50, max: 200)"),
  },
  async ({ job_id, problems_only, limit }) => {
    const params = new URLSearchParams();
    if (problems_only) params.set("problems_only", "true");
    if (limit) params.set("limit", String(limit));

    const result = await gateway("GET", `/jobs/${job_id}/pages?${params}`);
    if (!result.pages?.length) return { content: [{ type: "text", text: "No pages found." }] };

    const lines = result.pages.map((p) => {
      let line = `${p.url} (${p.status_code ?? "?"})`;
      line += ` | title: ${p.title_status} | desc: ${p.meta_desc_status} | h1s: ${p.h1_count}`;
      line += ` | words: ${p.word_count} | imgs w/o alt: ${p.images_no_alt}`;
      if (p.mixed_content) line += " | MIXED CONTENT";
      return line;
    });
    return { content: [{ type: "text", text: `${result.pages.length} page(s):\n\n${lines.join("\n")}` }] };
  }
);

// ── query_db ─────────────────────────────────────────────────────────
server.tool(
  "query_db",
  "Run a read-only SQL query against the SEO audit database. Tables: crawl_jobs, page_audits, site_issues, site_summaries. Views: v_latest_audits, v_critical_issues, v_problem_pages.",
  {
    sql: z.string().describe("A SELECT SQL query. Available tables: crawl_jobs, page_audits, site_issues, site_summaries."),
  },
  async ({ sql }) => {
    const params = new URLSearchParams({ sql });
    const result = await gateway("GET", `/query?${params}`);

    if (!result.rows?.length) return { content: [{ type: "text", text: "Query returned no results." }] };

    const cols = result.columns;
    const header = cols.join(" | ");
    const separator = cols.map((c) => "-".repeat(Math.max(c.length, 3))).join("-+-");
    const rows = result.rows.map((r) =>
      cols.map((c) => String(r[c] ?? "")).join(" | ")
    );

    return { content: [{ type: "text", text: `${result.count} row(s):\n\n${header}\n${separator}\n${rows.join("\n")}` }] };
  }
);

// ─── Start ───────────────────────────────────────────────────────────

const transport = new StdioServerTransport();
await server.connect(transport);
