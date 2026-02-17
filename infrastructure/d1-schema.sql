-- =============================================================================
-- Cloudflare D1 Schema for SEO Audit Platform
-- =============================================================================
-- Design principles:
--   1. Queryable metadata in indexed columns (domain, url, score, severity)
--   2. Full audit JSON stored for completeness (no data loss)
--   3. Flat issues table for "show me all critical issues" queries
--   4. Jobs table for tracking crawl lifecycle
-- =============================================================================

-- ─── Crawl Jobs ──────────────────────────────────────────────────────────────
-- Tracks every crawl request from submission through completion.
-- The Worker creates a row on submit; the Docker container updates it.

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id          TEXT PRIMARY KEY,                -- UUID
    domain      TEXT NOT NULL,                   -- e.g. "example.com"
    start_url   TEXT NOT NULL,                   -- entry URL for the crawl
    config      TEXT DEFAULT '{}',               -- JSON: depth, max_pages, filters, etc.
    status      TEXT NOT NULL DEFAULT 'queued',  -- queued | running | completed | failed
    pages_found INTEGER DEFAULT 0,
    pages_done  INTEGER DEFAULT 0,
    score       INTEGER,                         -- 0-100 site-wide SEO score (set on complete)
    error       TEXT,                            -- error message if failed
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    started_at  TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_domain ON crawl_jobs(domain);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON crawl_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON crawl_jobs(created_at);


-- ─── Page Audits ─────────────────────────────────────────────────────────────
-- One row per audited page. Key metrics in columns; full result as JSON.

CREATE TABLE IF NOT EXISTS page_audits (
    id              TEXT PRIMARY KEY,            -- UUID
    job_id          TEXT NOT NULL REFERENCES crawl_jobs(id),
    url             TEXT NOT NULL,
    domain          TEXT NOT NULL,
    status_code     INTEGER,

    -- Key SEO signals (indexed for fast queries)
    title           TEXT,
    title_length    INTEGER,
    title_status    TEXT,                        -- pass | fail | warning | info
    meta_desc       TEXT,
    meta_desc_length INTEGER,
    meta_desc_status TEXT,
    h1_count        INTEGER DEFAULT 0,
    has_canonical   INTEGER DEFAULT 0,           -- boolean: 0/1
    is_indexable    INTEGER DEFAULT 1,           -- boolean: 0/1
    has_json_ld     INTEGER DEFAULT 0,           -- boolean: 0/1
    has_viewport    INTEGER DEFAULT 0,           -- boolean: 0/1
    has_og_tags     INTEGER DEFAULT 0,           -- boolean: 0/1
    word_count      INTEGER DEFAULT 0,
    images_total    INTEGER DEFAULT 0,
    images_no_alt   INTEGER DEFAULT 0,
    internal_links  INTEGER DEFAULT 0,
    external_links  INTEGER DEFAULT 0,
    mixed_content   INTEGER DEFAULT 0,           -- boolean: 0/1

    -- Full audit result (all checks, all details)
    audit_json      TEXT NOT NULL,               -- JSON: complete PageAuditResult

    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pages_job    ON page_audits(job_id);
CREATE INDEX IF NOT EXISTS idx_pages_domain ON page_audits(domain);
CREATE INDEX IF NOT EXISTS idx_pages_url    ON page_audits(url);
CREATE INDEX IF NOT EXISTS idx_pages_title_status ON page_audits(title_status);
CREATE INDEX IF NOT EXISTS idx_pages_h1     ON page_audits(h1_count);


-- ─── Site Issues ─────────────────────────────────────────────────────────────
-- Flat table of all issues found in a site audit. One row per issue.
-- This is the primary table Claude queries: "show critical issues for domain X"

CREATE TABLE IF NOT EXISTS site_issues (
    id              TEXT PRIMARY KEY,            -- UUID
    job_id          TEXT NOT NULL REFERENCES crawl_jobs(id),
    domain          TEXT NOT NULL,
    issue_type      TEXT NOT NULL,               -- e.g. "missing_title", "duplicate_titles"
    severity        TEXT NOT NULL,               -- critical | warning | info
    description     TEXT NOT NULL,
    fix             TEXT,                        -- recommended fix
    affected_count  INTEGER DEFAULT 0,           -- number of affected pages
    affected_urls   TEXT,                        -- JSON array of affected URLs
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_issues_job      ON site_issues(job_id);
CREATE INDEX IF NOT EXISTS idx_issues_domain   ON site_issues(domain);
CREATE INDEX IF NOT EXISTS idx_issues_severity ON site_issues(severity);
CREATE INDEX IF NOT EXISTS idx_issues_type     ON site_issues(issue_type);


-- ─── Site Audit Summaries ────────────────────────────────────────────────────
-- One row per completed site audit. Quick dashboard-level data.

CREATE TABLE IF NOT EXISTS site_summaries (
    id              TEXT PRIMARY KEY,            -- same as job_id
    job_id          TEXT NOT NULL REFERENCES crawl_jobs(id),
    domain          TEXT NOT NULL,
    pages_audited   INTEGER DEFAULT 0,
    score           INTEGER DEFAULT 0,           -- 0-100
    issues_critical INTEGER DEFAULT 0,
    issues_warning  INTEGER DEFAULT 0,
    issues_info     INTEGER DEFAULT 0,
    audit_json      TEXT NOT NULL,               -- JSON: complete SiteAuditResult (minus page_details)
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_summary_domain ON site_summaries(domain);
CREATE INDEX IF NOT EXISTS idx_summary_score  ON site_summaries(score);


-- ─── Useful Views ────────────────────────────────────────────────────────────

-- Latest audit per domain (for "what's the current state of example.com?")
CREATE VIEW IF NOT EXISTS v_latest_audits AS
SELECT s.*, j.start_url, j.status as job_status, j.completed_at
FROM site_summaries s
JOIN crawl_jobs j ON j.id = s.job_id
WHERE j.status = 'completed'
ORDER BY s.created_at DESC;

-- All critical issues across all domains
CREATE VIEW IF NOT EXISTS v_critical_issues AS
SELECT si.*, j.start_url, j.completed_at
FROM site_issues si
JOIN crawl_jobs j ON j.id = si.job_id
WHERE si.severity = 'critical'
  AND j.status = 'completed'
ORDER BY si.created_at DESC;

-- Pages with SEO problems (quick filter)
CREATE VIEW IF NOT EXISTS v_problem_pages AS
SELECT
    pa.url,
    pa.domain,
    pa.title_status,
    pa.meta_desc_status,
    pa.h1_count,
    pa.has_canonical,
    pa.is_indexable,
    pa.word_count,
    pa.images_no_alt,
    pa.job_id,
    pa.created_at
FROM page_audits pa
WHERE pa.title_status = 'fail'
   OR pa.meta_desc_status = 'fail'
   OR pa.h1_count = 0
   OR pa.has_viewport = 0
   OR pa.mixed_content = 1;
