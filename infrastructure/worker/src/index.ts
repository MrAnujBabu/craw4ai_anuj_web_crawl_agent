/**
 * SEO Audit Gateway — Cloudflare Worker + Container
 *
 * The Worker is the API gateway. Each crawl job gets its own Container
 * instance (Durable Object), identified by job_id. The Container runs
 * crawl4ai + SEO audit inside a Docker image.
 *
 * Flow:
 *   1. POST /crawl          → Worker creates job in D1, spawns Container by job_id
 *   2. Container runs audit  → POSTs results to its own /results endpoint
 *   3. CrawlerContainer.onStart() → container HTTP server starts listening
 *   4. Worker proxies /start to container, which begins the crawl
 *   5. Container finishes    → calls back to the DO, which writes to D1
 *
 * Query routes (for the MCP DB tool):
 *   GET  /jobs               List jobs
 *   GET  /jobs/:id           Get job + summary
 *   GET  /jobs/:id/pages     Get page audits
 *   GET  /jobs/:id/issues    Get issues
 *   GET  /jobs/:id/status    Poll container status
 *   GET  /query              Read-only SQL
 */

import { Container } from "@cloudflare/containers";

// ═══════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════

export interface Env {
	DB: D1Database;
	SNAPSHOTS: R2Bucket;
	CRAWLER: DurableObjectNamespace;
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

	// Keep container alive for 30 min of idle time (crawls can be long)
	sleepAfter = "30m";

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
// Worker — API Gateway
// ═══════════════════════════════════════════════════════════════════════

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		// ── Auth ─────────────────────────────────────────────────
		const authHeader = request.headers.get("Authorization") || "";
		const token = authHeader.replace("Bearer ", "");
		if (token !== env.API_KEY) {
			return json({ error: "Unauthorized" }, 401);
		}

		const url = new URL(request.url);
		const path = url.pathname;
		const method = request.method;

		try {
			// ── POST /crawl ──────────────────────────────────────
			if (method === "POST" && path === "/crawl") {
				return handleSubmitCrawl(request, env);
			}

			// ── GET /jobs ────────────────────────────────────────
			if (method === "GET" && path === "/jobs") {
				return handleListJobs(url, env);
			}

			// ── GET /jobs/:id ────────────────────────────────────
			const jobMatch = path.match(/^\/jobs\/([a-f0-9-]+)$/);
			if (method === "GET" && jobMatch) {
				return handleGetJob(jobMatch[1], env);
			}

			// ── GET /jobs/:id/pages ──────────────────────────────
			const pagesMatch = path.match(/^\/jobs\/([a-f0-9-]+)\/pages$/);
			if (method === "GET" && pagesMatch) {
				return handleGetPages(pagesMatch[1], url, env);
			}

			// ── GET /jobs/:id/issues ─────────────────────────────
			const issuesMatch = path.match(/^\/jobs\/([a-f0-9-]+)\/issues$/);
			if (method === "GET" && issuesMatch) {
				return handleGetIssues(issuesMatch[1], url, env);
			}

			// ── GET /jobs/:id/status ─────────────────────────────
			const statusMatch = path.match(/^\/jobs\/([a-f0-9-]+)\/status$/);
			if (method === "GET" && statusMatch) {
				return handlePollStatus(statusMatch[1], env);
			}

			// ── GET /query ───────────────────────────────────────
			if (method === "GET" && path === "/query") {
				return handleQuery(url, env);
			}

			return json({ error: "Not found" }, 404);
		} catch (err: any) {
			console.error("Handler error:", err);
			return json({ error: err.message || "Internal error" }, 500);
		}
	},
};

// ═══════════════════════════════════════════════════════════════════════
// Route Handlers
// ═══════════════════════════════════════════════════════════════════════

async function handleSubmitCrawl(request: Request, env: Env): Promise<Response> {
	const body = (await request.json()) as {
		url: string;
		max_pages?: number;
		max_depth?: number;
	};

	if (!body.url) {
		return json({ error: "url is required" }, 400);
	}

	const domain = new URL(body.url).hostname;
	const jobId = crypto.randomUUID();
	const maxPages = body.max_pages ?? parseInt(env.MAX_PAGES_DEFAULT);
	const maxDepth = body.max_depth ?? parseInt(env.MAX_DEPTH_DEFAULT);
	const config = JSON.stringify({ max_pages: maxPages, max_depth: maxDepth });

	// 1. Create job record in D1
	await env.DB.prepare(
		`INSERT INTO crawl_jobs (id, domain, start_url, config, status)
		 VALUES (?, ?, ?, ?, 'queued')`
	)
		.bind(jobId, domain, body.url, config)
		.run();

	// 2. Get a Container instance keyed by job_id
	//    Each job gets its own container so crawls are isolated
	const containerId = env.CRAWLER.idFromName(jobId);
	const container = env.CRAWLER.get(containerId);

	// 3. Send the crawl request to the container's HTTP server
	//    The container image runs a Python HTTP server on port 8000
	try {
		const containerResp = await container.fetch(
			new Request("http://container/start", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					job_id: jobId,
					url: body.url,
					max_pages: maxPages,
					max_depth: maxDepth,
				}),
			})
		);

		if (!containerResp.ok) {
			const errText = await containerResp.text();
			throw new Error(`Container rejected start: ${errText}`);
		}

		// Update job status to running
		await env.DB.prepare(
			`UPDATE crawl_jobs SET status = 'running', started_at = datetime('now')
			 WHERE id = ?`
		)
			.bind(jobId)
			.run();
	} catch (err: any) {
		await env.DB.prepare(
			`UPDATE crawl_jobs SET status = 'failed', error = ? WHERE id = ?`
		)
			.bind(`Container start failed: ${err.message}`, jobId)
			.run();
		return json({ error: "Failed to start crawler container", job_id: jobId }, 502);
	}

	return json({ job_id: jobId, status: "running", domain }, 201);
}

async function handlePollStatus(jobId: string, env: Env): Promise<Response> {
	// First check D1 for the job
	const job = await env.DB.prepare(
		"SELECT id, status, score, pages_found, pages_done, error FROM crawl_jobs WHERE id = ?"
	)
		.bind(jobId)
		.first();

	if (!job) return json({ error: "Job not found" }, 404);

	// If already completed or failed, just return from D1
	if (job.status === "completed" || job.status === "failed") {
		return json(job);
	}

	// Otherwise poll the container for live progress
	try {
		const containerId = env.CRAWLER.idFromName(jobId);
		const container = env.CRAWLER.get(containerId);
		const resp = await container.fetch(new Request("http://container/status"));

		if (resp.ok) {
			const containerStatus = (await resp.json()) as any;

			// If container reports done, ingest results
			if (containerStatus.status === "completed" && containerStatus.results) {
				await ingestResults(jobId, containerStatus.results, env);
				return json({
					id: jobId,
					status: "completed",
					score: containerStatus.results.summary?.score,
					pages_done: containerStatus.results.pages?.length ?? 0,
				});
			}

			// Still running — return progress
			return json({
				id: jobId,
				status: "running",
				pages_done: containerStatus.pages_done ?? 0,
				pages_found: containerStatus.pages_found ?? 0,
			});
		}
	} catch {
		// Container might not be ready yet
	}

	return json(job);
}

async function handleListJobs(url: URL, env: Env): Promise<Response> {
	const domain = url.searchParams.get("domain");
	const status = url.searchParams.get("status");
	const limit = Math.min(parseInt(url.searchParams.get("limit") || "20"), 100);

	let query =
		"SELECT id, domain, start_url, status, score, pages_found, pages_done, created_at, completed_at FROM crawl_jobs WHERE 1=1";
	const params: string[] = [];

	if (domain) {
		query += " AND domain = ?";
		params.push(domain);
	}
	if (status) {
		query += " AND status = ?";
		params.push(status);
	}

	query += " ORDER BY created_at DESC LIMIT ?";
	params.push(String(limit));

	const result = await env.DB.prepare(query).bind(...params).all();
	return json({ jobs: result.results });
}

async function handleGetJob(jobId: string, env: Env): Promise<Response> {
	const job = await env.DB.prepare("SELECT * FROM crawl_jobs WHERE id = ?")
		.bind(jobId)
		.first();

	if (!job) return json({ error: "Job not found" }, 404);

	const summary = await env.DB.prepare(
		"SELECT * FROM site_summaries WHERE job_id = ?"
	)
		.bind(jobId)
		.first();

	return json({ job, summary });
}

async function handleGetPages(
	jobId: string,
	url: URL,
	env: Env
): Promise<Response> {
	const limit = Math.min(parseInt(url.searchParams.get("limit") || "50"), 200);
	const offset = parseInt(url.searchParams.get("offset") || "0");
	const problemsOnly = url.searchParams.get("problems_only") === "true";

	let query: string;
	if (problemsOnly) {
		query = `SELECT id, url, domain, status_code, title, title_status, meta_desc_status,
		         h1_count, has_canonical, is_indexable, word_count, images_no_alt, mixed_content,
		         created_at
		         FROM page_audits
		         WHERE job_id = ?
		           AND (title_status = 'fail' OR meta_desc_status = 'fail'
		                OR h1_count = 0 OR has_viewport = 0 OR mixed_content = 1)
		         ORDER BY url LIMIT ? OFFSET ?`;
	} else {
		query = `SELECT id, url, domain, status_code, title, title_status, meta_desc_status,
		         h1_count, has_canonical, is_indexable, word_count, images_no_alt, mixed_content,
		         created_at
		         FROM page_audits WHERE job_id = ?
		         ORDER BY url LIMIT ? OFFSET ?`;
	}

	const result = await env.DB.prepare(query).bind(jobId, limit, offset).all();
	return json({ pages: result.results, count: result.results?.length || 0 });
}

async function handleGetIssues(
	jobId: string,
	url: URL,
	env: Env
): Promise<Response> {
	const severity = url.searchParams.get("severity");

	let query = "SELECT * FROM site_issues WHERE job_id = ?";
	const params: string[] = [jobId];

	if (severity) {
		query += " AND severity = ?";
		params.push(severity);
	}

	query +=
		" ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END";

	const result = await env.DB.prepare(query).bind(...params).all();
	return json({ issues: result.results });
}

async function handleQuery(url: URL, env: Env): Promise<Response> {
	const sql = url.searchParams.get("sql");
	if (!sql) return json({ error: "sql parameter required" }, 400);

	// Read-only enforcement
	const normalized = sql.trim().toUpperCase();
	const forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE"];
	if (forbidden.some((kw) => normalized.startsWith(kw))) {
		return json({ error: "Only SELECT queries allowed" }, 403);
	}

	const result = await env.DB.prepare(sql).all();
	return json({
		columns: result.results?.[0] ? Object.keys(result.results[0]) : [],
		rows: result.results,
		count: result.results?.length || 0,
	});
}

// ═══════════════════════════════════════════════════════════════════════
// Result Ingestion — writes container output into D1
// ═══════════════════════════════════════════════════════════════════════

async function ingestResults(jobId: string, results: any, env: Env): Promise<void> {
	const domain =
		(
			await env.DB.prepare("SELECT domain FROM crawl_jobs WHERE id = ?")
				.bind(jobId)
				.first<{ domain: string }>()
		)?.domain || "";

	// Insert page audits
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
				crypto.randomUUID(),
				jobId,
				p.url,
				domain,
				p.status_code ?? null,
				p.title ?? null,
				p.title_length ?? null,
				p.title_status ?? null,
				p.meta_desc ?? null,
				p.meta_desc_length ?? null,
				p.meta_desc_status ?? null,
				p.h1_count ?? 0,
				p.has_canonical ? 1 : 0,
				p.is_indexable ? 1 : 0,
				p.has_json_ld ? 1 : 0,
				p.has_viewport ? 1 : 0,
				p.has_og_tags ? 1 : 0,
				p.word_count ?? 0,
				p.images_total ?? 0,
				p.images_no_alt ?? 0,
				p.internal_links ?? 0,
				p.external_links ?? 0,
				p.mixed_content ? 1 : 0,
				p.audit_json ?? "{}"
			)
		);
		await env.DB.batch(batch);
	}

	// Insert issues
	if (results.issues?.length) {
		const stmt = env.DB.prepare(
			`INSERT INTO site_issues (id, job_id, domain, issue_type, severity,
			 description, fix, affected_count, affected_urls)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
		);

		const batch = results.issues.map((i: any) =>
			stmt.bind(
				crypto.randomUUID(),
				jobId,
				domain,
				i.issue_type,
				i.severity,
				i.description,
				i.fix ?? null,
				i.affected_count ?? 0,
				JSON.stringify(i.affected_urls ?? [])
			)
		);
		await env.DB.batch(batch);
	}

	// Insert summary
	if (results.summary) {
		const s = results.summary;
		await env.DB.prepare(
			`INSERT INTO site_summaries (id, job_id, domain, pages_audited, score,
			 issues_critical, issues_warning, issues_info, audit_json)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
		)
			.bind(
				crypto.randomUUID(),
				jobId,
				domain,
				s.pages_audited ?? 0,
				s.score ?? 0,
				s.issues_critical ?? 0,
				s.issues_warning ?? 0,
				s.issues_info ?? 0,
				s.audit_json ?? "{}"
			)
			.run();
	}

	// Store HTML snapshots in R2
	if (results.snapshots?.length) {
		for (const snap of results.snapshots) {
			const key = `${jobId}/${encodeURIComponent(snap.url)}.html`;
			await env.SNAPSHOTS.put(key, snap.html);
		}
	}

	// Mark job as completed
	await env.DB.prepare(
		`UPDATE crawl_jobs
		 SET status = 'completed',
		     pages_done = ?,
		     score = ?,
		     completed_at = datetime('now')
		 WHERE id = ?`
	)
		.bind(results.pages?.length ?? 0, results.summary?.score ?? null, jobId)
		.run();
}

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
