-- US-Listed Filings Full DB Builder - PostgreSQL Schema
-- Version: 1.0
-- Date: 2025-10-28

-- Core company registry
-- Note: Same CIK can have multiple tickers (e.g., different share classes, ADRs)
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    cik VARCHAR(10) NOT NULL,
    company_name VARCHAR(255),
    exchange VARCHAR(20) NOT NULL,  -- 'NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca', etc.
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, exchange)
);

CREATE INDEX IF NOT EXISTS idx_companies_cik ON companies(cik);
CREATE INDEX IF NOT EXISTS idx_companies_ticker ON companies(ticker);
CREATE INDEX IF NOT EXISTS idx_companies_exchange ON companies(exchange) WHERE is_active = true;

-- Filings metadata (immutable once filed)
CREATE TABLE IF NOT EXISTS filings (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    accession_number VARCHAR(25) NOT NULL,
    form_type VARCHAR(10) NOT NULL,
    filing_date DATE NOT NULL,
    report_date DATE,
    fiscal_year INTEGER NOT NULL,
    fiscal_period VARCHAR(5),
    is_amendment BOOLEAN DEFAULT false,
    amends_accession VARCHAR(25),
    primary_document VARCHAR(255),
    document_count INTEGER,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(accession_number),
    FOREIGN KEY (amends_accession) REFERENCES filings(accession_number) DEFERRABLE
);

CREATE INDEX IF NOT EXISTS idx_filings_company ON filings(company_id);
CREATE INDEX IF NOT EXISTS idx_filings_date ON filings(filing_date);
CREATE INDEX IF NOT EXISTS idx_filings_form_year ON filings(form_type, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_filings_accession ON filings(accession_number);
CREATE INDEX IF NOT EXISTS idx_filings_amendments ON filings(amends_accession) WHERE amends_accession IS NOT NULL;

-- Artifact tracking (download status + integrity)
CREATE TABLE IF NOT EXISTS artifacts (
    id SERIAL PRIMARY KEY,
    filing_id INTEGER NOT NULL REFERENCES filings(id) ON DELETE CASCADE,
    artifact_type VARCHAR(20) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    local_path VARCHAR(512),
    url TEXT NOT NULL,
    file_size BIGINT,
    sha256 CHAR(64),
    status VARCHAR(20) DEFAULT 'pending_download',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    last_attempt_at TIMESTAMP,
    downloaded_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(filing_id, filename)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_filing ON artifacts(filing_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_status ON artifacts(status) WHERE status NOT IN ('downloaded', 'skipped');
CREATE INDEX IF NOT EXISTS idx_artifacts_retry ON artifacts(retry_count, status) 
    WHERE status = 'failed' AND retry_count < max_retries;
-- SHA256索引用于内容查找和复用，但不强制唯一（不同报告可能引用相同图片）
CREATE INDEX IF NOT EXISTS idx_artifacts_sha256 ON artifacts(sha256) WHERE sha256 IS NOT NULL;
-- 唯一约束：同一报告的同一URL只下载一次
CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_filing_url_unique ON artifacts(filing_id, url);

-- Retry queue (separate for better observability)
CREATE TABLE IF NOT EXISTS retry_queue (
    id SERIAL PRIMARY KEY,
    artifact_id INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    scheduled_for TIMESTAMP NOT NULL,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(artifact_id)
);

CREATE INDEX IF NOT EXISTS idx_retry_queue_schedule ON retry_queue(scheduled_for, priority);

-- Execution audit trail
CREATE TABLE IF NOT EXISTS execution_runs (
    id SERIAL PRIMARY KEY,
    run_type VARCHAR(50) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    filings_discovered INTEGER DEFAULT 0,
    artifacts_attempted INTEGER DEFAULT 0,
    artifacts_succeeded INTEGER DEFAULT 0,
    artifacts_failed INTEGER DEFAULT 0,
    duration_seconds INTEGER,
    error_summary TEXT,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_execution_runs_type ON execution_runs(run_type, started_at DESC);

-- Error log for detailed debugging
CREATE TABLE IF NOT EXISTS error_logs (
    id SERIAL PRIMARY KEY,
    execution_run_id INTEGER REFERENCES execution_runs(id),
    artifact_id INTEGER REFERENCES artifacts(id),
    error_type VARCHAR(50),
    error_message TEXT,
    stack_trace TEXT,
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_error_logs_run ON error_logs(execution_run_id);
CREATE INDEX IF NOT EXISTS idx_error_logs_artifact ON error_logs(artifact_id);
CREATE INDEX IF NOT EXISTS idx_error_logs_type ON error_logs(error_type, occurred_at DESC);

-- Weekly update tracking
CREATE TABLE IF NOT EXISTS incremental_updates (
    id SERIAL PRIMARY KEY,
    execution_run_id INTEGER NOT NULL REFERENCES execution_runs(id),
    lookback_start DATE NOT NULL,
    lookback_end DATE NOT NULL,
    companies_scanned INTEGER,
    new_filings_found INTEGER,
    sla_met BOOLEAN,
    success_rate NUMERIC(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_incremental_updates_date ON incremental_updates(lookback_end DESC);
