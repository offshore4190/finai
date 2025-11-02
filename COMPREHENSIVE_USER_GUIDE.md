# Filings ETL Comprehensive Operator Guide

This guide walks production operators through every step of installing, configuring, running, and maintaining the **US-Listed Filings ETL** pipeline. It expands on the high-level README by providing day‑to‑day procedures, safety checks, and troubleshooting tactics for completing coverage of 2023‑2025 10‑K/10‑Q filings (HTML + images) for NASDAQ and NYSE.

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture & Data Flow](#architecture--data-flow)
3. [Prerequisites](#prerequisites)
4. [Environment Configuration](#environment-configuration)
5. [Database Initialization](#database-initialization)
6. [Storage Layout](#storage-layout)
7. [End-to-End Runbook](#end-to-end-runbook)
8. [Download & Artifact Management](#download--artifact-management)
9. [Monitoring & Auditing](#monitoring--auditing)
10. [Testing & Verification](#testing--verification)
11. [Troubleshooting & FAQ](#troubleshooting--faq)
12. [Reference Appendix](#reference-appendix)

---

## System Overview

- **Purpose**: Build and maintain a complete PostgreSQL + filesystem dataset of SEC 10‑K/10‑Q filings from 2023–2025 for all NASDAQ and NYSE listings.
- **Scope**: ~13k SEC filers ingested; ~6k NASDAQ/NYSE companies targeted for artifact downloads.
- **Outputs**:
  - `companies`, `filings`, `artifacts` tables populated with audited metadata.
  - Local/S3 storage tree containing HTML, localized images, and XBRL resources.
  - Structured logs and execution run history for compliance.
- **Key Characteristics**:
  - Idempotent operations via SHA256 dedupe and retry queues.
  - SEC-compliant rate limiting (≤10 requests/sec total).
  - Modular jobs: listings ingestion, exchange enrichment, backfill, incremental updates.

---

## Architecture & Data Flow

```
┌───────────────┐     ┌────────────────────┐
│ SEC Company   │     │ NASDAQ / NYSE      │
│ Tickers API   │     │ Listings Reference │
└──────┬────────┘     └────────┬───────────┘
       │                         │
       ▼                         ▼
┌───────────────┐        ┌───────────────┐
│ companies     │        │ listings_ref  │
└──────┬────────┘        └────────┬──────┘
       │ Exchange Enrichment      │
       └──────────────┬───────────┘
                      ▼
               ┌──────────────┐
               │ filings      │
               ├──────────────┤
               │ artifacts    │──► Storage (/data/filings or S3)
               └──────────────┘
                      │
                      ▼
            Monitoring & Execution Logs
```

- **Listings Build** (`jobs/listings_build.py`): loads all SEC filers into `companies`.
- **Listings Reference Sync** (`jobs/listings_ref_sync.py`): pulls authoritative listings files into `listings_ref`.
- **Exchange Enrichment** (`jobs/exchange_enrichment.py`): updates `companies.exchange` (UNKNOWN → NASDAQ/NYSE variants).
- **Backfill Jobs**:
  - `jobs/backfill.py`: baseline sequential backfill.
  - `backfill_concurrent.py`: optimized async backfill respecting rate limits.
- **Incremental Updates** (`jobs/incremental.py`): weekly deltas and retry queue processing.
- **Artifact Downloader** (`services/downloader.py`): ensures HTML + images stored with integrity checks.

---

## Prerequisites

| Requirement           | Minimum                          | Recommended                         |
|-----------------------|----------------------------------|-------------------------------------|
| OS                    | Linux / macOS / Windows (WSL)    | Linux or macOS                      |
| Python                | 3.10+ (pydantic v2 requirement)  | 3.11                                |
| PostgreSQL            | 14                               | 15                                  |
| Disk Space            | 100 GB free                      | 500 GB SSD                          |
| Memory                | 4 GB                             | 8 GB                                |
| Network               | Stable internet, SEC-friendly UA | 10 Mbps+ downstream                 |

> **Tip**: Activate a virtual environment to isolate dependencies: `python -m venv .venv && source .venv/bin/activate`.

---

## Environment Configuration

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Prepare Environment File**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set/confirm:
   - `SEC_USER_AGENT` (REQUIRED): `CompanyName ContactEmail`
   - Database connection values (`DB_HOST`, `DB_NAME`, etc.)
   - Storage root (`STORAGE_ROOT`) if using local storage
   - Download worker count (`DOWNLOAD_WORKERS`, default 8, ≤10)

3. **Key Settings (`config/settings.py`)**
   - `sec_rate_limit`: max SEC RPS (default 10).
   - `artifact_retry_max`: capped retries for failed artifacts (default 3).
   - `incremental_lookback_days`: window for incremental scans (default 7).
   - Validation ensures `SEC_USER_AGENT` includes email and workers ≤10.

---

## Database Initialization

1. **Start PostgreSQL**
   - Local service: `brew services start postgresql` (macOS) / `sudo systemctl start postgresql` (Linux).
   - Docker Compose: `docker-compose up -d postgres`.

2. **Create Schema**
   ```bash
   python main.py init-db
   ```
   This executes migrations in `migrations/`:
   - Base schema (companies, filings, artifacts, execution_runs, etc.)
   - Listings reference table
   - CIK constraint adjustments and dedupes

3. **Verify Connectivity**
   ```bash
   psql postgresql://user:pass@host:port/filings_db -c "\dt"
   ```
   Ensure tables like `companies`, `filings`, `artifacts`, `listings_ref` exist.

---

## Storage Layout

- Default root: `/data/filings` (configurable via `STORAGE_ROOT`).
- Structure: `/{exchange}/{ticker}/{year}/` containing HTML, localized images, and XBRL subdirectories.
  ```
  /data/filings/NASDAQ/AAPL/2024/
    ├── aapl-20240201_10q.html
    ├── aapl-20240201_10q_image001.png
    └── xbrl/
        └── aapl-20240201_cal.xml
  ```
- Ensure filesystem permissions allow the ETL process to create nested directories.

---

## End-to-End Runbook

### 1. Bootstrap Listings
```bash
python main.py listings
```
- Ingests ~13k SEC filers into `companies` with `exchange='UNKNOWN'`.
- Idempotent: rerunning updates ticker metadata without duplication.

### 2. Sync Exchange References
```bash
python main.py listings-ref-sync
```
- Downloads latest NASDAQ + NYSE reference CSVs into `data/listings_ref/`.
- Populates `listings_ref` table with exchange mapping and ETF flags.

### 3. Enrich Company Exchanges
```bash
python main.py exchange-enrichment
```
- Updates `companies.exchange` using `listings_ref`.
- Result categories: `NASDAQ`, `NYSE`, `NYSE American`, `NYSE Arca`, `UNKNOWN`.
- Safe to rerun after each reference sync.

### 4. Historical Backfill (Baseline)
```bash
python main.py backfill            # full ~6k companies
python main.py backfill --limit 50 # smoke test
```
- Scans 2023-01-01 to 2025-12-31 for forms `10-K`, `10-K/A`, `10-Q`, `10-Q/A`.
- Creates `filings` rows and `artifacts` entries with `status='pending_download'`.
- Honors SEC rate limits via download worker configuration.

### 5. Concurrent Backfill (Optimized)
```bash
python backfill_concurrent.py \
  --batch-size 25 \
  --max-concurrent-companies 10 \
  --max-concurrent-downloads 8
```
- Async pipeline combining discovery + downloads.
- Automatically creates `execution_runs` audit records.
- Adjust concurrency to keep global RPS ≤8–10 (use `--max-concurrent-downloads` ≤ `DOWNLOAD_WORKERS`).
- Use `--no-download` for metadata-only discovery (follow with download loop).

### 6. Process Pending Downloads
```bash
python process_pending_downloads.py --batch-size 50 --max-concurrent 8
```
- Fetches `artifacts` with `status='pending_download'`.
- Downloads HTML + images using `ArtifactDownloader`, updating status to `downloaded`/`failed`.
- Options: `--exchange`, `--limit`, `--nyse-only`.

### 7. Incremental Updates
```bash
python main.py incremental
```
- Looks back `incremental_lookback_days` (default 7) for new filings.
- Requeues failed artifacts, downloads new ones, records SLA metrics.
- Schedule via cron/automation.

### 8. Routine Audits
Use audit scripts to verify coverage and queue health:
```bash
python diagnose_coverage.py
python monitor_backfill_progress.py
```
- Reports coverage percentages, retry queues, and outstanding gaps.

---

## Download & Artifact Management

### Repair Failed Artifacts
`repair_failed_artifacts.py` requeues failed downloads (default NYSE-only).
```bash
python repair_failed_artifacts.py --batch-size 200
```
- Reads `settings.artifact_retry_max` (default 3) to skip exhausted retries.
- Update/extend to support other exchanges (e.g., add `--exchange` flag when enhancing).

### Backfill Safety Controls
- `settings.download_workers` validated between 1 and 10.
- `ArtifactDownloader` deduplicates by SHA256 to avoid redundant downloads.
- Retry logic: exponential backoff, capped by `artifact_retry_max`.

### Idempotency Tips
- The system checks for existing `filings.accession_number`; rerunning backfills is safe.
- Storage writes based on deterministic path; re-download overwrites only if checksum differs.
- Use dry-run enhancements (if added) before large requeues/backfills in production.

---

## Monitoring & Auditing

### Logs
- Structured logging via `structlog`; format configurable (`LOG_FORMAT=json|console`).
- Key log files under `logs/` (e.g., `download_loop.log`, incremental/backfill logs).
- Tailing logs:
  ```bash
  tail -f logs/backfill_2024-*.log
  tail -f download_loop.log
  ```

### Database Dashboards
- `execution_runs`: status per job (start/end, duration, stats).
  ```sql
  SELECT run_type, status, started_at, completed_at, metadata
  FROM execution_runs
  ORDER BY started_at DESC LIMIT 10;
  ```
- Coverage checks:
  ```sql
  SELECT exchange, COUNT(*) AS companies,
         SUM(CASE WHEN filings_count > 0 THEN 1 ELSE 0 END) AS with_filings
  FROM (
    SELECT c.id, c.exchange, COUNT(f.id) AS filings_count
    FROM companies c
    LEFT JOIN filings f ON f.company_id = c.id
      AND f.filing_date BETWEEN '2023-01-01' AND '2025-12-31'
    GROUP BY c.id, c.exchange
  ) t
  GROUP BY exchange;
  ```

### Shell Monitoring Helpers
- `monitor_progress.sh`: lightweight dashboard for backfill progress.
- `monitor_rate_limit.sh`: checks SEC rate limit headroom.
- `watch_downloads.sh`: continuously processes pending artifacts in batches.

---

## Testing & Verification

1. **Unit/Integration Tests**
   ```bash
   python -m pytest
   ```
   > **Note**: The pytest suite relies on plugins (`pytest-postgresql`) requiring Python ≥3.10 due to `typing` union syntax.

2. **Smoke Tests**
   - Run `python main.py backfill --limit 5` on staging DB.
   - Execute `process_pending_downloads.py --limit 10` to validate artifact pipeline.

3. **Data Validation**
   - Use `diagnose_coverage.py` to compare expected vs downloaded artifacts.
   - Inspect sample filesystem output to ensure HTML and associated images exist.

---

## Troubleshooting & FAQ

### Common Issues

| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| `SEC_USER_AGENT must be customized` | Default value left in `.env` | Update `.env` with company + contact email, rerun command |
| Downloads stuck at `pending_download` | Rate limit hit or network failure | Run `repair_failed_artifacts.py` then `process_pending_downloads.py`; check network + logs |
| `psycopg.OperationalError` connecting to DB | DB credentials incorrect | Verify `.env` values, ensure PostgreSQL running |
| Pytest failure `unsupported operand type(s) for |` | Python <3.10 interpreter | Upgrade virtualenv to Python 3.10+ |
| Excessive SEC 429 errors | Too many concurrent downloads | Reduce `DOWNLOAD_WORKERS`/`--max-concurrent-downloads`; ensure proper sleeps between batches |

### Best Practices
- Throttle concurrency when running multiple scripts simultaneously.
- Always tail logs during long backfills to detect failures early.
- Schedule periodic audits (daily during catch-up, weekly afterward).
- Keep historical logs archived for compliance.
- Regularly refresh NASDAQ/NYSE listings (monthly recommended).

---

## Reference Appendix

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL connection | `localhost`, `5432`, `filings_db`, `postgres`, `postgres` |
| `STORAGE_ROOT` | Local storage root | `/data/filings` |
| `STORAGE_BACKEND` | `local` or `s3` | `local` |
| `S3_BUCKET`, `S3_REGION` | S3 configuration (if enabled) | `None`, `us-east-1` |
| `SEC_USER_AGENT` | Required SEC user agent | _no default (must set)_ |
| `SEC_RATE_LIMIT` | Max RPS | `10` |
| `DOWNLOAD_WORKERS` | Concurrent downloader workers | `8` |
| `ARTIFACT_RETRY_MAX` | Retry cap per artifact | `3` |
| `INCREMENTAL_LOOKBACK_DAYS` | Incremental scan window | `7` |
| `LOG_FORMAT` | `json` or `console` | `json` |

### CLI Command Summary

| Command | Description |
|---------|-------------|
| `python main.py init-db` | Run all migrations and initialize schema |
| `python main.py listings` | Ingest master SEC company list |
| `python main.py listings-ref-sync` | Sync NASDAQ/NYSE reference listings |
| `python main.py exchange-enrichment` | Update company exchanges from references |
| `python main.py backfill [--limit N]` | Discover filings and queue artifacts |
| `python main.py incremental` | Weekly incremental discovery/download |
| `python backfill_concurrent.py [...]` | Async backfill with bounded concurrency |
| `python process_pending_downloads.py [...]` | Download artifacts currently pending |
| `python repair_failed_artifacts.py [...]` | Requeue failed artifacts for retry |
| `python diagnose_coverage.py` | Summarize data coverage and gaps |

### Key Directories

- `config/`: Settings, DB session helpers.
- `jobs/`: Primary ETL steps (listings, backfill, incremental).
- `services/`: Reusable clients (SEC API, downloader, storage).
- `migrations/`: SQL schema definitions.
- `tests/`: Integration + unit tests.
- `logs/`: Runtime logs and dashboards.
- `data/`: Output artifacts (filings, listings references, etc.).

---

By following this guide, operators can confidently bootstrap the ETL environment, execute large backfills without violating SEC limits, monitor progress, and resolve failures quickly. Keep this document alongside the existing `USER_GUIDE.md` for a concise yet comprehensive reference when resuming operations after interruptions or onboarding new teammates.

