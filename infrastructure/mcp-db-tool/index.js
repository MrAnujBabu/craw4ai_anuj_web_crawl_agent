/**
 * SEO Audit MCP Tool — Database query interface for Claude.
 *
 * Connects to the Cloudflare Worker gateway and exposes 5 tools:
 *   1. submit_crawl    — Start a new SEO audit crawl
 *   2. list_jobs       — List crawl jobs (filter by domain/status)
 *   3. get_job         — Get job details + audit summary
 *   4. get_issues      — Get SEO issues for a job
 *   5. query_db        — Run arbitrary read-only SQL against D1
 *
 * Configuration (env vars):
 *   GATEWAY_URL  — Base URL of the CF Worker (e.g. https://seo-audit-gateway.you.workers.dev)
 *   API_KEY      — Bearer token for the Worker
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const GATEWAY_URL = process.env.GATEWAY_URL || "http://localhost:8787";
const API_KEY = process.env.API_KEY || "";

// ─── Tool Definitions ────────────────────────────────────────────────

const TOOLS = [
  {
    name: "submit_crawl",
    description:
      "Start a new SEO audit crawl for a website. Returns a job_id you can use to check status and retrieve results.",
    inputSchema: {
      type: "object",
      properties: {
        url: {
          type: "string",
          description: "The starting URL to crawl (e.g. https://example.com)",
        },
        max_pages: {
          type: "number",
          description: "Maximum pages to crawl (default: 50)",
        },
        max_depth: {
          type: "number",
          description: "Maximum crawl depth from start URL (default: 3)",
        },
      },
      required: ["url"],
    },
  },
  {
    name: "list_jobs",
    description:
      "List SEO audit jobs. Filter by domain and/or status (queued, running, completed, failed).",
    inputSchema: {
      type: "object",
      properties: {
        domain: {
          type: "string",
          description: "Filter by domain (e.g. example.com)",
        },
        status: {
          type: "string",
          enum: ["queued", "running", "completed", "failed"],
          description: "Filter by job status",
        },
        limit: {
          type: "number",
          description: "Max results to return (default: 20, max: 100)",
        },
      },
    },
  },
  {
    name: "get_job",
    description:
      "Get full details for a specific audit job, including the site-wide summary with SEO score, issue counts, and page stats.",
    inputSchema: {
      type: "object",
      properties: {
        job_id: {
          type: "string",
          description: "The job UUID",
        },
      },
      required: ["job_id"],
    },
  },
  {
    name: "get_issues",
    description:
      "Get all SEO issues found for a crawl job. Can filter by severity (critical, warning, info). Returns issue type, description, fix recommendation, and affected URLs.",
    inputSchema: {
      type: "object",
      properties: {
        job_id: {
          type: "string",
          description: "The job UUID",
        },
        severity: {
          type: "string",
          enum: ["critical", "warning", "info"],
          description: "Filter by severity level",
        },
      },
      required: ["job_id"],
    },
  },
  {
    name: "query_db",
    description:
      "Run a read-only SQL query against the SEO audit database. Tables: crawl_jobs, page_audits, site_issues, site_summaries. Views: v_latest_audits, v_critical_issues, v_problem_pages. Use this for custom analysis.",
    inputSchema: {
      type: "object",
      properties: {
        sql: {
          type: "string",
          description:
            "A SELECT SQL query. Available tables: crawl_jobs, page_audits, site_issues, site_summaries. Views: v_latest_audits, v_critical_issues, v_problem_pages.",
        },
      },
      required: ["sql"],
    },
  },
];

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

// ─── Tool Handler ────────────────────────────────────────────────────

async function handleTool(name, args) {
  switch (name) {
    case "submit_crawl": {
      const result = await gateway("POST", "/crawl", {
        url: args.url,
        max_pages: args.max_pages,
        max_depth: args.max_depth,
      });
      return `Crawl job submitted.\n\nJob ID: ${result.job_id}\nDomain: ${result.domain}\nStatus: ${result.status}\n\nUse get_job with this job_id to check progress. Once completed, use get_issues to see findings.`;
    }

    case "list_jobs": {
      const params = new URLSearchParams();
      if (args.domain) params.set("domain", args.domain);
      if (args.status) params.set("status", args.status);
      if (args.limit) params.set("limit", String(args.limit));

      const result = await gateway("GET", `/jobs?${params}`);
      if (!result.jobs?.length) return "No jobs found matching your criteria.";

      const lines = result.jobs.map(
        (j) =>
          `- ${j.id} | ${j.domain} | ${j.status} | score: ${j.score ?? "—"} | ${j.pages_done ?? 0} pages | ${j.created_at}`
      );
      return `Found ${result.jobs.length} job(s):\n\n${lines.join("\n")}`;
    }

    case "get_job": {
      const result = await gateway("GET", `/jobs/${args.job_id}`);
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
      return out;
    }

    case "get_issues": {
      const params = new URLSearchParams();
      if (args.severity) params.set("severity", args.severity);

      const result = await gateway(
        "GET",
        `/jobs/${args.job_id}/issues?${params}`
      );
      if (!result.issues?.length) return "No issues found.";

      const lines = result.issues.map((i) => {
        const urls = i.affected_urls
          ? JSON.parse(i.affected_urls).slice(0, 5)
          : [];
        let line = `[${i.severity.toUpperCase()}] ${i.issue_type}: ${i.description}`;
        if (i.fix) line += `\n  Fix: ${i.fix}`;
        if (urls.length)
          line += `\n  Affected: ${urls.join(", ")}${i.affected_count > 5 ? ` (+${i.affected_count - 5} more)` : ""}`;
        return line;
      });

      return `Found ${result.issues.length} issue(s):\n\n${lines.join("\n\n")}`;
    }

    case "query_db": {
      const params = new URLSearchParams({ sql: args.sql });
      const result = await gateway("GET", `/query?${params}`);

      if (!result.rows?.length) return "Query returned no results.";

      // Format as a readable table
      const cols = result.columns;
      const header = cols.join(" | ");
      const separator = cols.map((c) => "-".repeat(c.length)).join("-+-");
      const rows = result.rows.map((r) =>
        cols.map((c) => String(r[c] ?? "")).join(" | ")
      );

      return `${result.count} row(s):\n\n${header}\n${separator}\n${rows.join("\n")}`;
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

// ─── MCP Server ──────────────────────────────────────────────────────

const server = new Server(
  { name: "seo-audit-db", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS,
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  try {
    const text = await handleTool(name, args || {});
    return { content: [{ type: "text", text }] };
  } catch (err) {
    return {
      content: [{ type: "text", text: `Error: ${err.message}` }],
      isError: true,
    };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
