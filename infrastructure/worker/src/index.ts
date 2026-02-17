/**
 * SEO Audit Gateway — Cloudflare Worker + MCP Server + Container
 *
 * This Worker serves dual roles:
 *   1. MCP Server (via agents/mcp) — Claude connects directly via /mcp/{token}
 *   2. REST API Gateway — backward-compatible HTTP API for the stdio MCP tool
 *
 * Architecture:
 *   Claude ──MCP──→ Worker (SEOAuditMcpAgent DO) ──→ D1/R2/Container
 *   Claude ──stdio──→ mcp-db-tool ──REST──→ Worker fetch handler ──→ D1/R2/Container
 *
 * Auth:
 *   - MCP routes: token in URL path /mcp/{token} (like DataForSEO MCP pattern)
 *   - REST routes: Bearer token in Authorization header
 *
 * Container: Each crawl job gets its own CF Container (Durable Object),
 * running crawl4ai + SEO audit in a Docker image.
 */

import { McpAgent } from "agents/mcp";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { Container } from "@cloudflare/containers";

// ═══════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════

export interface Env {
	DB: D1Database;
	SNAPSHOTS: R2Bucket;
	CRAWLER: DurableObjectNamespace;
	MCP_OBJECT: DurableObjectNamespace;
	API_KEY: string;
	ENVIRONMENT: string;
	MAX_PAGES_DEFAULT: string;
	MAX_DEPTH_DEFAULT: string;
}

// ═══════════════════════════════════════════════════════════════════════
// CrawlerContainer — Durable Object wrapping the Docker container
// ═══════════════════════════════════════════════════════════════════════

export class CrawlerContainer extends Container {
	defaultPort = 8000;
	sleepAfter = "5m";

	override onStart(): void {
		console.log("[CrawlerContainer] Container started");
	}

	override onStop(): void {
		console.log("[CrawlerContainer] Container stopped");
	}

	override onError(error: unknown): void {
		console.error("[CrawlerContainer] Container error:", error);
	}
}

// ═══════════════════════════════════════════════════════════════════════
// SEOAuditMcpAgent — MCP Server as Durable Object (agents/mcp pattern)
// ═══════════════════════════════════════════════════════════════════════

export class SEOAuditMcpAgent extends McpAgent {
	server = new McpServer({
		name: "seo-audit-mcp",
		version: "1.0.0",
	});

	constructor(ctx: DurableObjectState, protected env: Env) {
		super(ctx, env);
	}

	async init() {
		const workerEnv = this.env || (globalThis as any).workerEnv;
		if (!workerEnv) {
			throw new Error("Worker environment not available");
		}

		// ── submit_crawl ─────────────────────────────────────────
		this.server.tool(
			"submit_crawl",
			"Start a new SEO audit crawl for a website. Returns a job_id to check status and retrieve results.",
			{
				url: z.string().describe("The starting URL to crawl (e.g. https://example.com)"),
				max_pages: z.number().optional().describe("Maximum pages to crawl (default: 50)"),
				max_depth: z.number().optional().describe("Maximum crawl depth from start URL (default: 3)"),
			},
			async (args) => {
				const result = await submitCrawl(workerEnv, args.url, args.max_pages, args.max_depth);
				return {
					content: [{
						type: "text" as const,
						text: `Crawl job submitted. A Cloudflare Container is spinning up.\n\nJob ID: ${result.job_id}\nDomain: ${result.domain}\nStatus: ${result.status}\n\nUse poll_job to check progress. Once completed, use get_issues to see findings.`,
					}],
				};
			}
		);

		// ── poll_job ─────────────────────────────────────────────
		this.server.tool(
			"poll_job",
			"Poll the live status of a running crawl job. Returns progress or final results.",
			{
				job_id: z.string().describe("The job UUID from submit_crawl"),
			},
			async (args) => {
				const result = await pollJob(workerEnv, args.job_id);
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
				return { content: [{ type: "text" as const, text: out }] };
			}
		);

		// ── list_jobs ────────────────────────────────────────────
		this.server.tool(
			"list_jobs",
			"List SEO audit jobs. Filter by domain and/or status.",
			{
				domain: z.string().optional().describe("Filter by domain (e.g. example.com)"),
				status: z.enum(["queued", "running", "completed", "failed"]).optional().describe("Filter by job status"),
				limit: z.number().optional().describe("Max results (default: 20, max: 100)"),
			},
			async (args) => {
				const jobs = await listJobs(workerEnv, args.domain, args.status, args.limit);
				if (!jobs.length) return { content: [{ type: "text" as const, text: "No jobs found matching your criteria." }] };

				const lines = jobs.map(
					(j: any) => `- ${j.id} | ${j.domain} | ${j.status} | score: ${j.score ?? "—"} | ${j.pages_done ?? 0} pages | ${j.created_at}`
				);
				return { content: [{ type: "text" as const, text: `Found ${jobs.length} job(s):\n\n${lines.join("\n")}` }] };
			}
		);

		// ── get_job ──────────────────────────────────────────────
		this.server.tool(
			"get_job",
			"Get full details for a specific audit job, including the site-wide summary with SEO score.",
			{
				job_id: z.string().describe("The job UUID"),
			},
			async (args) => {
				const { job, summary } = await getJob(workerEnv, args.job_id);
				let out = `Job: ${job.id}\nDomain: ${job.domain}\nURL: ${job.start_url}\nStatus: ${job.status}`;
				out += `\nCreated: ${job.created_at}`;
				if (job.completed_at) out += `\nCompleted: ${job.completed_at}`;
				if (job.error) out += `\nError: ${job.error}`;

				if (summary) {
					out += `\n\n── Site Audit Summary ──`;
					out += `\nSEO Score: ${summary.score}/100`;
					out += `\nPages Audited: ${summary.pages_audited}`;
					out += `\nCritical Issues: ${summary.issues_critical}`;
					out += `\nWarnings: ${summary.issues_warning}`;
					out += `\nInfo: ${summary.issues_info}`;
				}
				return { content: [{ type: "text" as const, text: out }] };
			}
		);

		// ── get_issues ───────────────────────────────────────────
		this.server.tool(
			"get_issues",
			"Get all SEO issues found for a crawl job. Filter by severity. Returns issue type, description, fix, and affected URLs.",
			{
				job_id: z.string().describe("The job UUID"),
				severity: z.enum(["critical", "warning", "info"]).optional().describe("Filter by severity level"),
			},
			async (args) => {
				const issues = await getIssues(workerEnv, args.job_id, args.severity);
				if (!issues.length) return { content: [{ type: "text" as const, text: "No issues found." }] };

				const lines = issues.map((i: any) => {
					const urls = i.affected_urls ? JSON.parse(i.affected_urls).slice(0, 5) : [];
					let line = `[${i.severity.toUpperCase()}] ${i.issue_type}: ${i.description}`;
					if (i.fix) line += `\n  Fix: ${i.fix}`;
					if (urls.length)
						line += `\n  Affected: ${urls.join(", ")}${i.affected_count > 5 ? ` (+${i.affected_count - 5} more)` : ""}`;
					return line;
				});
				return { content: [{ type: "text" as const, text: `Found ${issues.length} issue(s):\n\n${lines.join("\n\n")}` }] };
			}
		);

		// ── get_pages ────────────────────────────────────────────
		this.server.tool(
			"get_pages",
			"Get page-level audit details for a crawl job. Can filter to only pages with problems.",
			{
				job_id: z.string().describe("The job UUID"),
				problems_only: z.boolean().optional().describe("Only return pages with SEO problems (default: false)"),
				limit: z.number().optional().describe("Max results (default: 50, max: 200)"),
				offset: z.number().optional().describe("Offset for pagination (default: 0)"),
			},
			async (args) => {
				const pages = await getPages(workerEnv, args.job_id, args.problems_only, args.limit, args.offset);
				if (!pages.length) return { content: [{ type: "text" as const, text: "No pages found." }] };

				const lines = pages.map((p: any) => {
					let line = `${p.url} (${p.status_code ?? "?"})`;
					line += ` | title: ${p.title_status} | desc: ${p.meta_desc_status} | h1s: ${p.h1_count}`;
					line += ` | words: ${p.word_count} | imgs w/o alt: ${p.images_no_alt}`;
					if (p.mixed_content) line += " | MIXED CONTENT";
					return line;
				});
				return { content: [{ type: "text" as const, text: `${pages.length} page(s):\n\n${lines.join("\n")}` }] };
			}
		);

		// ── query_db ─────────────────────────────────────────────
		this.server.tool(
			"query_db",
			"Run a read-only SQL query against the SEO audit database. Tables: crawl_jobs, page_audits, site_issues, site_summaries. Views: v_latest_audits, v_critical_issues, v_problem_pages.",
			{
				sql: z.string().describe("A SELECT SQL query against the audit database"),
			},
			async (args) => {
				const result = await queryDb(workerEnv, args.sql);
				if (!result.rows.length) return { content: [{ type: "text" as const, text: "Query returned no results." }] };

				const cols = result.columns;
				const header = cols.join(" | ");
				const separator = cols.map((c: string) => "-".repeat(Math.max(c.length, 3))).join("-+-");
				const rows = result.rows.map((r: any) =>
					cols.map((c: string) => String(r[c] ?? "")).join(" | ")
				);
				return {
					content: [{
						type: "text" as const,
						text: `${result.rows.length} row(s):\n\n${header}\n${separator}\n${rows.join("\n")}`,
					}],
				};
			}
		);
	}
}

// ═══════════════════════════════════════════════════════════════════════
// Shared Business Logic (used by both MCP tools and REST endpoints)
// ═══════════════════════════════════════════════════════════════════════

async function submitCrawl(
	env: Env,
	url: string,
	maxPages?: number,
	maxDepth?: number
): Promise<{ job_id: string; status: string; domain: string }> {
	const domain = new URL(url).hostname;
	const jobId = crypto.randomUUID();
	const pages = maxPages ?? parseInt(env.MAX_PAGES_DEFAULT || "50");
	const depth = maxDepth ?? parseInt(env.MAX_DEPTH_DEFAULT || "3");
	const config = JSON.stringify({ max_pages: pages, max_depth: depth });

	await env.DB.prepare(
		`INSERT INTO crawl_jobs (id, domain, start_url, config, status)
		 VALUES (?, ?, ?, ?, 'queued')`
	).bind(jobId, domain, url, config).run();

	const containerId = env.CRAWLER.idFromName(jobId);
	const container = env.CRAWLER.get(containerId);

	try {
		const containerResp = await container.fetch(
			new Request("http://container/start", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ job_id: jobId, url, max_pages: pages, max_depth: depth }),
			})
		);

		if (!containerResp.ok) {
			const errText = await containerResp.text();
			throw new Error(`Container rejected start: ${errText}`);
		}

		await env.DB.prepare(
			`UPDATE crawl_jobs SET status = 'running', started_at = datetime('now') WHERE id = ?`
		).bind(jobId).run();
	} catch (err: any) {
		await env.DB.prepare(
			`UPDATE crawl_jobs SET status = 'failed', error = ? WHERE id = ?`
		).bind(`Container start failed: ${err.message}`, jobId).run();
		throw new Error(`Failed to start crawler container: ${err.message}`);
	}

	return { job_id: jobId, status: "running", domain };
}

async function pollJob(env: Env, jobId: string): Promise<any> {
	const job = await env.DB.prepare(
		"SELECT id, status, score, pages_found, pages_done, error FROM crawl_jobs WHERE id = ?"
	).bind(jobId).first();

	if (!job) throw new Error("Job not found");

	if (job.status === "completed" || job.status === "failed") {
		return job;
	}

	try {
		const containerId = env.CRAWLER.idFromName(jobId);
		const container = env.CRAWLER.get(containerId);
		const resp = await container.fetch(new Request("http://container/status"));

		if (resp.ok) {
			const containerStatus = (await resp.json()) as any;

			if (containerStatus.status === "completed" && containerStatus.results) {
				await ingestResults(jobId, containerStatus.results, env);
				return {
					id: jobId,
					status: "completed",
					score: containerStatus.results.summary?.score,
					pages_done: containerStatus.results.pages?.length ?? 0,
				};
			}

			return {
				id: jobId,
				status: "running",
				pages_done: containerStatus.pages_done ?? 0,
				pages_found: containerStatus.pages_found ?? 0,
			};
		}
	} catch {
		// Container might not be ready yet
	}

	return job;
}

async function listJobs(
	env: Env,
	domain?: string,
	status?: string,
	limit?: number
): Promise<any[]> {
	const maxLimit = Math.min(limit || 20, 100);
	let query = "SELECT id, domain, start_url, status, score, pages_found, pages_done, created_at, completed_at FROM crawl_jobs WHERE 1=1";
	const params: string[] = [];

	if (domain) { query += " AND domain = ?"; params.push(domain); }
	if (status) { query += " AND status = ?"; params.push(status); }

	query += " ORDER BY created_at DESC LIMIT ?";
	params.push(String(maxLimit));

	const result = await env.DB.prepare(query).bind(...params).all();
	return result.results || [];
}

async function getJob(env: Env, jobId: string): Promise<{ job: any; summary: any }> {
	const job = await env.DB.prepare("SELECT * FROM crawl_jobs WHERE id = ?").bind(jobId).first();
	if (!job) throw new Error("Job not found");

	const summary = await env.DB.prepare("SELECT * FROM site_summaries WHERE job_id = ?").bind(jobId).first();
	return { job, summary };
}

async function getIssues(env: Env, jobId: string, severity?: string): Promise<any[]> {
	let query = "SELECT * FROM site_issues WHERE job_id = ?";
	const params: string[] = [jobId];

	if (severity) { query += " AND severity = ?"; params.push(severity); }

	query += " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END";

	const result = await env.DB.prepare(query).bind(...params).all();
	return result.results || [];
}

async function getPages(
	env: Env,
	jobId: string,
	problemsOnly?: boolean,
	limit?: number,
	offset?: number
): Promise<any[]> {
	const maxLimit = Math.min(limit || 50, 200);
	const off = offset || 0;

	let query: string;
	if (problemsOnly) {
		query = `SELECT id, url, domain, status_code, title, title_status, meta_desc_status,
		         h1_count, has_canonical, is_indexable, word_count, images_no_alt, mixed_content, created_at
		         FROM page_audits
		         WHERE job_id = ?
		           AND (title_status = 'fail' OR meta_desc_status = 'fail'
		                OR h1_count = 0 OR has_viewport = 0 OR mixed_content = 1)
		         ORDER BY url LIMIT ? OFFSET ?`;
	} else {
		query = `SELECT id, url, domain, status_code, title, title_status, meta_desc_status,
		         h1_count, has_canonical, is_indexable, word_count, images_no_alt, mixed_content, created_at
		         FROM page_audits WHERE job_id = ?
		         ORDER BY url LIMIT ? OFFSET ?`;
	}

	const result = await env.DB.prepare(query).bind(jobId, maxLimit, off).all();
	return result.results || [];
}

async function queryDb(env: Env, sql: string): Promise<{ columns: string[]; rows: any[] }> {
	const normalized = sql.trim().toUpperCase();
	const forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE"];
	if (forbidden.some((kw) => normalized.startsWith(kw))) {
		throw new Error("Only SELECT queries allowed");
	}

	const result = await env.DB.prepare(sql).all();
	return {
		columns: result.results?.[0] ? Object.keys(result.results[0]) : [],
		rows: result.results || [],
	};
}

// ═══════════════════════════════════════════════════════════════════════
// Result Ingestion — writes container output into D1
// ═══════════════════════════════════════════════════════════════════════

async function ingestResults(jobId: string, results: any, env: Env): Promise<void> {
	const domain =
		(await env.DB.prepare("SELECT domain FROM crawl_jobs WHERE id = ?")
			.bind(jobId).first<{ domain: string }>())?.domain || "";

	if (results.pages?.length) {
		const stmt = env.DB.prepare(
			`INSERT INTO page_audits (id, job_id, url, domain, status_code,
			 title, title_length, title_status, meta_desc, meta_desc_length, meta_desc_status,
			 h1_count, has_canonical, is_indexable, has_json_ld, has_viewport, has_og_tags,
			 word_count, images_total, images_no_alt, internal_links, external_links,
			 mixed_content, audit_json)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
		);

		const batch = results.pages.map((p: any) =>
			stmt.bind(
				crypto.randomUUID(), jobId, p.url, domain, p.status_code ?? null,
				p.title ?? null, p.title_length ?? null, p.title_status ?? null,
				p.meta_desc ?? null, p.meta_desc_length ?? null, p.meta_desc_status ?? null,
				p.h1_count ?? 0, p.has_canonical ? 1 : 0, p.is_indexable ? 1 : 0,
				p.has_json_ld ? 1 : 0, p.has_viewport ? 1 : 0, p.has_og_tags ? 1 : 0,
				p.word_count ?? 0, p.images_total ?? 0, p.images_no_alt ?? 0,
				p.internal_links ?? 0, p.external_links ?? 0,
				p.mixed_content ? 1 : 0, p.audit_json ?? "{}"
			)
		);
		await env.DB.batch(batch);
	}

	if (results.issues?.length) {
		const stmt = env.DB.prepare(
			`INSERT INTO site_issues (id, job_id, domain, issue_type, severity,
			 description, fix, affected_count, affected_urls)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
		);

		const batch = results.issues.map((i: any) =>
			stmt.bind(
				crypto.randomUUID(), jobId, domain,
				i.issue_type, i.severity, i.description,
				i.fix ?? null, i.affected_count ?? 0,
				JSON.stringify(i.affected_urls ?? [])
			)
		);
		await env.DB.batch(batch);
	}

	if (results.summary) {
		const s = results.summary;
		await env.DB.prepare(
			`INSERT INTO site_summaries (id, job_id, domain, pages_audited, score,
			 issues_critical, issues_warning, issues_info, audit_json)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
		).bind(
			crypto.randomUUID(), jobId, domain,
			s.pages_audited ?? 0, s.score ?? 0,
			s.issues_critical ?? 0, s.issues_warning ?? 0, s.issues_info ?? 0,
			s.audit_json ?? "{}"
		).run();
	}

	if (results.snapshots?.length) {
		for (const snap of results.snapshots) {
			const key = `${jobId}/${encodeURIComponent(snap.url)}.html`;
			await env.SNAPSHOTS.put(key, snap.html);
		}
	}

	await env.DB.prepare(
		`UPDATE crawl_jobs SET status = 'completed', pages_done = ?, score = ?, completed_at = datetime('now') WHERE id = ?`
	).bind(results.pages?.length ?? 0, results.summary?.score ?? null, jobId).run();
}

// ═══════════════════════════════════════════════════════════════════════
// Worker Fetch Handler
// ═══════════════════════════════════════════════════════════════════════

export default {
	async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
		const url = new URL(request.url);
		const path = url.pathname;
		const method = request.method;

		// Store env in global context for McpAgent access
		(globalThis as any).workerEnv = env;

		// ── Health check (no auth) ───────────────────────────────
		if (path === "/health" && method === "GET") {
			return json({
				status: "healthy",
				server: "seo-audit-mcp",
				version: "1.0.0",
				timestamp: new Date().toISOString(),
			});
		}

		// ── MCP Routes: /mcp/{token}, /sse/{token}, /sse/{token}/message ──
		const mcpMatch = path.match(/^\/(mcp|http|sse)\/(([^\/]+)(\/message)?)$/);
		if (mcpMatch) {
			const [, route, , token] = mcpMatch;
			if (!env.API_KEY || token !== env.API_KEY) {
				return json({ error: "forbidden" }, 403);
			}

			// Rewrite URL to strip token so the MCP handler sees clean paths
			const messageSuffix = path.endsWith("/message");
			const cleanPath = route === "sse" && messageSuffix ? "/sse/message" : `/${route}`;
			const rewrittenUrl = new URL(cleanPath, url.origin);
			rewrittenUrl.search = url.search;
			const rewrittenRequest = new Request(rewrittenUrl.toString(), request);

			if (route === "sse") {
				return SEOAuditMcpAgent.serveSSE("/sse").fetch(rewrittenRequest, env, ctx);
			}
			// mcp or http → streamable HTTP transport
			return SEOAuditMcpAgent.serve("/mcp").fetch(rewrittenRequest, env, ctx);
		}

		// Reject bare MCP paths without token
		if (["/mcp", "/http", "/sse", "/sse/message"].includes(path)) {
			return json({ error: "forbidden" }, 403);
		}

		// ── REST API Routes (Bearer token auth) ─────────────────
		const authHeader = request.headers.get("Authorization") || "";
		const bearerToken = authHeader.replace("Bearer ", "");
		if (bearerToken !== env.API_KEY) {
			return json({ error: "Unauthorized" }, 401);
		}

		try {
			if (method === "POST" && path === "/crawl") {
				const body = (await request.json()) as { url: string; max_pages?: number; max_depth?: number };
				if (!body.url) return json({ error: "url is required" }, 400);
				const result = await submitCrawl(env, body.url, body.max_pages, body.max_depth);
				return json(result, 201);
			}

			if (method === "GET" && path === "/jobs") {
				const domain = url.searchParams.get("domain") || undefined;
				const status = url.searchParams.get("status") || undefined;
				const limit = url.searchParams.get("limit") ? parseInt(url.searchParams.get("limit")!) : undefined;
				const jobs = await listJobs(env, domain, status, limit);
				return json({ jobs });
			}

			const jobMatch = path.match(/^\/jobs\/([a-f0-9-]+)$/);
			if (method === "GET" && jobMatch) {
				const result = await getJob(env, jobMatch[1]);
				return json(result);
			}

			const pagesMatch = path.match(/^\/jobs\/([a-f0-9-]+)\/pages$/);
			if (method === "GET" && pagesMatch) {
				const problemsOnly = url.searchParams.get("problems_only") === "true";
				const limit = url.searchParams.get("limit") ? parseInt(url.searchParams.get("limit")!) : undefined;
				const offset = url.searchParams.get("offset") ? parseInt(url.searchParams.get("offset")!) : undefined;
				const pages = await getPages(env, pagesMatch[1], problemsOnly, limit, offset);
				return json({ pages, count: pages.length });
			}

			const issuesMatch = path.match(/^\/jobs\/([a-f0-9-]+)\/issues$/);
			if (method === "GET" && issuesMatch) {
				const severity = url.searchParams.get("severity") || undefined;
				const issues = await getIssues(env, issuesMatch[1], severity);
				return json({ issues });
			}

			const statusMatch = path.match(/^\/jobs\/([a-f0-9-]+)\/status$/);
			if (method === "GET" && statusMatch) {
				const result = await pollJob(env, statusMatch[1]);
				return json(result);
			}

			if (method === "GET" && path === "/query") {
				const sql = url.searchParams.get("sql");
				if (!sql) return json({ error: "sql parameter required" }, 400);
				const result = await queryDb(env, sql);
				return json({ ...result, count: result.rows.length });
			}

			return json({ error: "Not found" }, 404);
		} catch (err: any) {
			console.error("Handler error:", err);
			return json({ error: err.message || "Internal error" }, 500);
		}
	},
};

// ═══════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════

function json(data: unknown, status = 200): Response {
	return new Response(JSON.stringify(data, null, 2), {
		status,
		headers: {
			"Content-Type": "application/json",
			"Access-Control-Allow-Origin": "*",
		},
	});
}
