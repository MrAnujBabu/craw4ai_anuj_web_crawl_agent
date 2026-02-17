/**
 * SEO Audit Gateway — Cloudflare Worker
 *
 * Routes:
 *   POST /crawl           Submit a new crawl job
 *   GET  /jobs             List jobs (filterable by domain, status)
 *   GET  /jobs/:id         Get job details + summary
 *   GET  /jobs/:id/pages   Get page-level audit results
 *   GET  /jobs/:id/issues  Get issues for a job
 *   GET  /query            Raw SQL query (read-only, for the MCP DB tool)
 *   POST /jobs/:id/results Worker-internal: Docker container posts results here
 */

export interface Env {
	DB: D1Database;
	SNAPSHOTS: R2Bucket;
	API_KEY: string;
	DOCKER_API_URL: string;
	ENVIRONMENT: string;
	MAX_PAGES_DEFAULT: string;
	MAX_DEPTH_DEFAULT: string;
}

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

			// ── GET /query ───────────────────────────────────────
			// Read-only SQL for the MCP DB query tool
			if (method === "GET" && path === "/query") {
				return handleQuery(url, env);
			}

			// ── POST /jobs/:id/results ───────────────────────────
			// Internal: Docker container posts results here
			const resultsMatch = path.match(/^\/jobs\/([a-f0-9-]+)\/results$/);
			if (method === "POST" && resultsMatch) {
				return handlePostResults(resultsMatch[1], request, env);
			}

			return json({ error: "Not found" }, 404);
		} catch (err: any) {
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
		config?: Record<string, unknown>;
	};

	if (!body.url) {
		return json({ error: "url is required" }, 400);
	}

	const domain = new URL(body.url).hostname;
	const jobId = crypto.randomUUID();
	const config = JSON.stringify({
		max_pages: body.max_pages ?? parseInt(env.MAX_PAGES_DEFAULT),
		max_depth: body.max_depth ?? parseInt(env.MAX_DEPTH_DEFAULT),
		...body.config,
	});

	// Insert job
	await env.DB.prepare(
		`INSERT INTO crawl_jobs (id, domain, start_url, config, status)
		 VALUES (?, ?, ?, ?, 'queued')`
	)
		.bind(jobId, domain, body.url, config)
		.run();

	// Trigger Docker container
	try {
		await fetch(env.DOCKER_API_URL, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				job_id: jobId,
				url: body.url,
				config: JSON.parse(config),
				callback_url: `${new URL(request.url).origin}/jobs/${jobId}/results`,
			}),
		});
	} catch {
		// If Docker trigger fails, mark job as failed
		await env.DB.prepare(
			`UPDATE crawl_jobs SET status = 'failed', error = 'Failed to start container'
			 WHERE id = ?`
		)
			.bind(jobId)
			.run();
		return json({ error: "Failed to start crawler", job_id: jobId }, 502);
	}

	return json({ job_id: jobId, status: "queued", domain }, 201);
}

async function handleListJobs(url: URL, env: Env): Promise<Response> {
	const domain = url.searchParams.get("domain");
	const status = url.searchParams.get("status");
	const limit = Math.min(parseInt(url.searchParams.get("limit") || "20"), 100);

	let query = "SELECT id, domain, start_url, status, score, pages_found, pages_done, created_at, completed_at FROM crawl_jobs WHERE 1=1";
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
	const job = await env.DB.prepare(
		"SELECT * FROM crawl_jobs WHERE id = ?"
	)
		.bind(jobId)
		.first();

	if (!job) return json({ error: "Job not found" }, 404);

	// Also fetch summary if completed
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
	const problems_only = url.searchParams.get("problems_only") === "true";

	let query: string;
	if (problems_only) {
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

	const result = await env.DB.prepare(query)
		.bind(jobId, limit, offset)
		.all();

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

	query += " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END";

	const result = await env.DB.prepare(query).bind(...params).all();
	return json({ issues: result.results });
}

async function handleQuery(url: URL, env: Env): Promise<Response> {
	const sql = url.searchParams.get("sql");
	if (!sql) return json({ error: "sql parameter required" }, 400);

	// Read-only enforcement: reject writes
	const normalized = sql.trim().toUpperCase();
	if (
		normalized.startsWith("INSERT") ||
		normalized.startsWith("UPDATE") ||
		normalized.startsWith("DELETE") ||
		normalized.startsWith("DROP") ||
		normalized.startsWith("ALTER") ||
		normalized.startsWith("CREATE")
	) {
		return json({ error: "Only SELECT queries allowed" }, 403);
	}

	const result = await env.DB.prepare(sql).all();
	return json({
		columns: result.results?.[0] ? Object.keys(result.results[0]) : [],
		rows: result.results,
		count: result.results?.length || 0,
	});
}

async function handlePostResults(
	jobId: string,
	request: Request,
	env: Env
): Promise<Response> {
	const body = (await request.json()) as {
		status: "completed" | "failed";
		error?: string;
		pages?: PageResult[];
		summary?: SummaryResult;
		issues?: IssueResult[];
		snapshots?: { url: string; html: string }[];
	};

	// Update job status
	if (body.status === "failed") {
		await env.DB.prepare(
			`UPDATE crawl_jobs SET status = 'failed', error = ?, completed_at = datetime('now')
			 WHERE id = ?`
		)
			.bind(body.error || "Unknown error", jobId)
			.run();
		return json({ ok: true });
	}

	const domain =
		(
			await env.DB.prepare("SELECT domain FROM crawl_jobs WHERE id = ?")
				.bind(jobId)
				.first<{ domain: string }>()
		)?.domain || "";

	// Insert page audits
	if (body.pages) {
		const stmt = env.DB.prepare(
			`INSERT INTO page_audits (id, job_id, url, domain, status_code,
			 title, title_length, title_status, meta_desc, meta_desc_length, meta_desc_status,
			 h1_count, has_canonical, is_indexable, has_json_ld, has_viewport, has_og_tags,
			 word_count, images_total, images_no_alt, internal_links, external_links,
			 mixed_content, audit_json)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
		);

		const batch = body.pages.map((p) =>
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
	if (body.issues) {
		const stmt = env.DB.prepare(
			`INSERT INTO site_issues (id, job_id, domain, issue_type, severity,
			 description, fix, affected_count, affected_urls)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
		);

		const batch = body.issues.map((i) =>
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
	if (body.summary) {
		await env.DB.prepare(
			`INSERT INTO site_summaries (id, job_id, domain, pages_audited, score,
			 issues_critical, issues_warning, issues_info, audit_json)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
		)
			.bind(
				crypto.randomUUID(),
				jobId,
				domain,
				body.summary.pages_audited ?? 0,
				body.summary.score ?? 0,
				body.summary.issues_critical ?? 0,
				body.summary.issues_warning ?? 0,
				body.summary.issues_info ?? 0,
				body.summary.audit_json ?? "{}"
			)
			.run();
	}

	// Store HTML snapshots in R2
	if (body.snapshots) {
		for (const snap of body.snapshots) {
			const key = `${jobId}/${encodeURIComponent(snap.url)}.html`;
			await env.SNAPSHOTS.put(key, snap.html);
		}
	}

	// Update job as completed
	await env.DB.prepare(
		`UPDATE crawl_jobs
		 SET status = 'completed',
		     pages_done = ?,
		     score = ?,
		     completed_at = datetime('now')
		 WHERE id = ?`
	)
		.bind(
			body.pages?.length ?? 0,
			body.summary?.score ?? null,
			jobId
		)
		.run();

	return json({ ok: true });
}

// ═══════════════════════════════════════════════════════════════════════
// Types for result ingestion
// ═══════════════════════════════════════════════════════════════════════

interface PageResult {
	url: string;
	status_code?: number;
	title?: string;
	title_length?: number;
	title_status?: string;
	meta_desc?: string;
	meta_desc_length?: number;
	meta_desc_status?: string;
	h1_count?: number;
	has_canonical?: boolean;
	is_indexable?: boolean;
	has_json_ld?: boolean;
	has_viewport?: boolean;
	has_og_tags?: boolean;
	word_count?: number;
	images_total?: number;
	images_no_alt?: number;
	internal_links?: number;
	external_links?: number;
	mixed_content?: boolean;
	audit_json?: string;
}

interface IssueResult {
	issue_type: string;
	severity: string;
	description: string;
	fix?: string;
	affected_count?: number;
	affected_urls?: string[];
}

interface SummaryResult {
	pages_audited?: number;
	score?: number;
	issues_critical?: number;
	issues_warning?: number;
	issues_info?: number;
	audit_json?: string;
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
