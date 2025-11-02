# US-Listed Filings ETL - User Guide

## Table of Contents
1. [Introduction](#introduction)
2. [What This System Does](#what-this-system-does)
3. [Who Should Use This](#who-should-use-this)
4. [System Requirements](#system-requirements)
5. [Getting Started](#getting-started)
6. [Understanding the System](#understanding-the-system)
7. [Step-by-Step Usage](#step-by-step-usage)
8. [Common Workflows](#common-workflows)
9. [Monitoring and Maintenance](#monitoring-and-maintenance)
10. [Troubleshooting](#troubleshooting)
11. [Best Practices](#best-practices)
12. [FAQ](#faq)

---

## Introduction

Welcome to the US-Listed Filings ETL System! This user guide will help you understand, set up, and operate this production-ready data pipeline for collecting SEC filings.

### What You'll Learn
- How to install and configure the system
- How to run the data pipeline
- How to monitor progress and health
- How to troubleshoot common issues
- Best practices for production use

### Documentation Overview
- **USER_GUIDE.md** (this file) - Complete user guide for operators
- **README.md** - Technical overview and quick reference
- **IMPLEMENTATION.md** - Architecture and design details
- **TESTING_GUIDE_CN.md** - Testing tutorial (Chinese)
- **QUICK_REFERENCE.md** - Command cheat sheet (Chinese)
- **TROUBLESHOOTING_CN.md** - Problem-solving guide (Chinese)

---

## What This System Does

### Overview
This system automatically collects, downloads, and organizes SEC filings (10-K and 10-Q reports) for companies listed on NASDAQ and NYSE exchanges.

### Key Capabilities
- **Comprehensive Coverage**: Downloads filings for ~6,000 NASDAQ and NYSE companies
- **Time Range**: Covers filings from 2023 to 2025
- **Complete Artifacts**: Fetches HTML documents, embedded images, and XBRL financial data
- **Automated Updates**: Weekly incremental updates for new filings
- **Smart Processing**: Deduplicates files, retries failures automatically
- **Compliance**: Respects SEC rate limits (10 requests/second)

### What You Get
After running the system, you'll have:
- A PostgreSQL database with all filing metadata
- Organized file storage with HTML documents and images
- XBRL financial data files
- Complete audit trail and error logs
- SLA metrics and performance reports

---

## Who Should Use This

### Ideal Users
- **Financial Analysts**: Access historical financial reports
- **Data Scientists**: Build datasets for machine learning
- **Researchers**: Analyze corporate disclosures
- **Compliance Teams**: Monitor regulatory filings
- **Software Engineers**: Integrate SEC data into applications

### Required Skills
- **Basic**: Command line usage, file system navigation
- **Intermediate**: Python basics, SQL queries
- **Advanced** (optional): Docker, PostgreSQL administration

### Not Required
- Deep Python programming knowledge
- SEC EDGAR API expertise
- Complex system administration

---

## System Requirements

### Minimum Requirements
- **Operating System**: Linux, macOS, or Windows with WSL
- **Python**: 3.10 or higher
- **PostgreSQL**: 14 or higher
- **Storage**: 100 GB available disk space
- **Memory**: 4 GB RAM
- **Network**: Stable internet connection

### Recommended Configuration
- **Storage**: 500 GB SSD (for full dataset)
- **Memory**: 8 GB RAM
- **Network**: 10 Mbps+ download speed
- **CPU**: 4+ cores (for parallel downloads)

### Software Dependencies
Automatically installed via `pip`:
- `httpx` - HTTP client
- `psycopg` - PostgreSQL adapter
- `sqlalchemy` - Database ORM
- `pydantic-settings` - Configuration management
- `beautifulsoup4` - HTML parsing
- `structlog` - Structured logging

---

## Getting Started

### Installation Steps

#### 1. Download and Extract
```bash
# If you have a ZIP file
unzip filings-etl.zip
cd filings-etl

# If you have a tar.gz file
tar -xzf filings-etl.tar.gz
cd filings-etl
```

#### 2. Set Up Python Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate

# Verify activation (you should see "(venv)" in your prompt)
```

#### 3. Install Dependencies
```bash
# Install all required packages
pip install -r requirements.txt

# Verify installation
pip list | grep httpx
```

#### 4. Set Up PostgreSQL

**Option A: Using Docker (Recommended)**
```bash
# Start PostgreSQL container
docker-compose up -d postgres

# Verify it's running
docker-compose ps
```

**Option B: Using Local PostgreSQL**
```bash
# Install PostgreSQL (if not already installed)
# macOS: brew install postgresql
# Ubuntu: sudo apt-get install postgresql

# Start PostgreSQL service
# macOS: brew services start postgresql
# Ubuntu: sudo systemctl start postgresql

# Create database
psql -U postgres -c "CREATE DATABASE filings_db;"
```

#### 5. Configure Environment
```bash
# Copy example configuration
cp .env.example .env

# Edit configuration (IMPORTANT!)
nano .env  # or use your preferred editor
```

**Critical Configuration**:
Edit `.env` and update the `SEC_USER_AGENT` line:
```bash
SEC_USER_AGENT=YourCompanyName contact@yourcompany.com
```

**Why This Matters**: The SEC requires a valid User-Agent with your contact information. Requests without proper User-Agent will be rejected.

#### 6. Initialize Database
```bash
# Create all tables and indexes
python main.py init-db

# Verify tables were created
psql -U postgres -d filings_db -c "\dt"
```

Expected output: 8 tables (companies, filings, artifacts, etc.)

#### 7. Verify Installation
```bash
# Run test suite
python run_tests.py

# You should see:
# ============================== 38 passed ===============================
```

Congratulations! Your system is now ready to use.

---

## Understanding the System

### System Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  Listings   │────▶│  Backfill   │────▶│ Incremental  │
│   Build     │     │             │     │   Updates    │
└─────────────┘     └─────────────┘     └──────────────┘
       │                   │                     │
       ▼                   ▼                     ▼
  ┌────────────────────────────────────────────────────┐
  │            SEC EDGAR API (Rate Limited)            │
  └────────────────────────────────────────────────────┘
       │                   │                     │
       ▼                   ▼                     ▼
  ┌──────────┐      ┌────────────┐      ┌──────────────┐
  │PostgreSQL│      │   Storage  │      │  Retry Queue │
  │ Metadata │      │   System   │      │   + Logs     │
  └──────────┘      └────────────┘      └──────────────┘
```

### Data Flow

1. **Listings Build**: Fetches list of all SEC-registered companies (~13,000)
2. **Listings Reference Sync**: Downloads official NASDAQ/NYSE listing files
3. **Exchange Enrichment**: Matches companies to exchanges, filters to ~6,000 target companies
4. **Backfill**: Discovers all 10-K and 10-Q filings (2023-2025) for target companies
5. **Download**: Fetches HTML, images, and XBRL files
6. **Incremental**: Weekly scan for new filings in the last 7 days

### Storage Structure

Files are organized as follows:
```
/data/filings/
├── NASDAQ/
│   └── AAPL/                          # Ticker symbol
│       └── 2023/                      # Year
│           ├── AAPL_2023_Q1_03-02-2023.html
│           ├── AAPL_2023_Q1_03-02-2023_image01.png
│           ├── AAPL_2023_Q1_03-02-2023_image02.png
│           └── xbrl/                  # XBRL data
│               ├── aapl-20230930.xsd
│               └── aapl-20230930_cal.xml
└── NYSE/
    └── JPM/
        └── 2024/
            └── ...
```

### Database Schema

**Key Tables**:
- `companies` - All SEC-registered companies with exchange info
- `listings_ref` - Official NASDAQ/NYSE listing reference data
- `filings` - Filing metadata (10-K, 10-Q, amendments)
- `artifacts` - Individual files (HTML, images, XBRL)
- `execution_runs` - Audit trail of all ETL runs
- `error_logs` - Detailed error information
- `retry_queue` - Failed downloads scheduled for retry
- `incremental_updates` - Weekly update metrics and SLA tracking

**Important Views**:
- `v_target_companies` - Filtered view of ~6,000 NASDAQ/NYSE companies (excludes ETFs and UNKNOWN exchanges)

---

## Step-by-Step Usage

### Initial Setup (First Time Only)

#### Step 1: Build Company Listings
This fetches all ~13,000 SEC-registered companies:
```bash
python main.py listings
```

**What happens**:
- Fetches company data from SEC API
- Populates `companies` table
- Initially sets all exchanges as 'UNKNOWN'
- Takes ~2-5 minutes

**Verify**:
```bash
psql -U postgres -d filings_db -c "SELECT COUNT(*) FROM companies;"
# Should show ~13,000
```

#### Step 2: Sync Exchange Reference Data
This downloads official NASDAQ and NYSE listing files:
```bash
python main.py listings-ref-sync
```

**What happens**:
- Downloads NASDAQ listed companies
- Downloads NYSE listed companies
- Populates `listings_ref` table with authoritative data
- Includes ETF flags for filtering
- Takes ~30 seconds

**Verify**:
```bash
psql -U postgres -d filings_db -c "SELECT COUNT(*) FROM listings_ref;"
# Should show several thousand entries
```

#### Step 3: Enrich Company Exchanges
This matches companies to their exchanges:
```bash
python main.py exchange-enrichment
```

**What happens**:
- Joins company tickers with reference data
- Updates exchange field from 'UNKNOWN' to actual exchanges
- Handles ticker conflicts (prefers non-ETF)
- Results in ~6,000 companies with proper exchange assignments
- Takes ~10 seconds

**Verify**:
```bash
psql -U postgres -d filings_db -c "
SELECT exchange, COUNT(*)
FROM companies
GROUP BY exchange
ORDER BY COUNT(*) DESC;
"
# Should show: NASDAQ, NYSE, NYSE American, NYSE Arca, UNKNOWN
```

#### Step 4: Backfill Historical Filings

**Test with small dataset first**:
```bash
python main.py backfill --limit 10
```

**What happens**:
- Processes first 10 companies from target view
- Fetches all 10-K and 10-Q filings (2023-2025)
- Creates records in `filings` and `artifacts` tables
- Takes ~5-10 minutes for 10 companies

**Verify**:
```bash
psql -U postgres -d filings_db -c "
SELECT
    c.ticker,
    COUNT(f.id) as filing_count
FROM companies c
JOIN filings f ON c.id = f.company_id
GROUP BY c.ticker
ORDER BY filing_count DESC
LIMIT 10;
"
```

**Run full backfill** (when ready):
```bash
python main.py backfill
```

**Important**: This processes all ~6,000 target companies and may take several hours. You can run it in the background:
```bash
nohup python main.py backfill > backfill.log 2>&1 &
```

Monitor progress:
```bash
tail -f backfill.log
```

### Regular Operations

#### Weekly Incremental Updates
Run this every week to get new filings:
```bash
python main.py incremental
```

**What happens**:
- Scans last 7 days for new filings
- Downloads new HTML, images, and XBRL files
- Retries previously failed downloads (up to 3 attempts)
- Records SLA metrics
- Takes ~1-6 hours depending on volume

**Set up automated weekly runs**:
```bash
# Edit crontab
crontab -e

# Add this line (runs every Monday at 2 AM)
0 2 * * 1 cd /path/to/filings-etl && /path/to/venv/bin/python main.py incremental >> logs/incremental.log 2>&1
```

---

## Common Workflows

### Workflow 1: First-Time Setup (Recommended)
For testing before full deployment:
```bash
# 1. Setup environment (one time)
source venv/bin/activate
python main.py init-db

# 2. Build company list
python main.py listings

# 3. Sync reference data
python main.py listings-ref-sync

# 4. Enrich exchanges
python main.py exchange-enrichment

# 5. Test with small dataset
python main.py backfill --limit 5

# 6. Check results
psql -U postgres -d filings_db -c "
SELECT status, COUNT(*) FROM artifacts GROUP BY status;
"

# 7. View downloaded files
ls -lh /data/filings/NASDAQ/

# 8. If all looks good, run full backfill
python main.py backfill
```

### Workflow 2: Weekly Maintenance
```bash
# Activate environment
source venv/bin/activate

# Run incremental update
python main.py incremental

# Check SLA compliance
psql -U postgres -d filings_db -c "
SELECT
    er.started_at,
    er.duration_seconds / 3600.0 AS hours,
    iu.success_rate,
    iu.sla_met
FROM execution_runs er
JOIN incremental_updates iu ON iu.execution_run_id = er.id
WHERE er.run_type = 'incremental'
ORDER BY er.started_at DESC
LIMIT 1;
"
```

### Workflow 3: Handling Failures
```bash
# 1. Check for failed downloads
psql -U postgres -d filings_db -c "
SELECT
    c.ticker,
    f.form_type,
    a.artifact_type,
    a.retry_count,
    a.error_message
FROM artifacts a
JOIN filings f ON a.filing_id = f.id
JOIN companies c ON f.company_id = c.id
WHERE a.status = 'failed'
  AND a.retry_count >= 3
LIMIT 10;
"

# 2. Check error logs
psql -U postgres -d filings_db -c "
SELECT error_type, error_message, occurred_at
FROM error_logs
ORDER BY occurred_at DESC
LIMIT 10;
"

# 3. Re-run incremental to retry failures
python main.py incremental
```

### Workflow 4: Adding New Companies
```bash
# When new companies are listed on exchanges:

# 1. Update company listings
python main.py listings

# 2. Sync latest reference data
python main.py listings-ref-sync

# 3. Enrich exchanges
python main.py exchange-enrichment

# 4. Backfill for new companies only
python main.py backfill
# (The system automatically skips existing companies)
```

### Workflow 5: Database Maintenance
```bash
# Weekly cleanup

# 1. Remove old error logs (older than 30 days)
psql -U postgres -d filings_db -c "
DELETE FROM error_logs
WHERE occurred_at < NOW() - INTERVAL '30 days';
"

# 2. Clean up completed retry queue entries
psql -U postgres -d filings_db -c "
DELETE FROM retry_queue rq
USING artifacts a
WHERE rq.artifact_id = a.id
  AND a.status = 'downloaded';
"

# 3. Vacuum database
psql -U postgres -d filings_db -c "VACUUM ANALYZE;"

# 4. Check database size
psql -U postgres -d filings_db -c "
SELECT pg_size_pretty(pg_database_size('filings_db'));
"
```

---

## Monitoring and Maintenance

### Real-Time Monitoring

#### Monitor Download Progress
```bash
# Option 1: Watch command (Linux/macOS)
watch -n 5 'psql -U postgres -d filings_db -c "SELECT status, COUNT(*) FROM artifacts GROUP BY status;"'

# Option 2: Manual refresh
while true; do
    clear
    psql -U postgres -d filings_db -c "SELECT status, COUNT(*) FROM artifacts GROUP BY status;"
    sleep 5
done
```

#### Check Execution Status
```bash
psql -U postgres -d filings_db -c "
SELECT
    run_type,
    started_at,
    ROUND(duration_seconds / 60.0, 2) as duration_minutes,
    artifacts_attempted,
    artifacts_succeeded,
    artifacts_failed
FROM execution_runs
ORDER BY started_at DESC
LIMIT 5;
"
```

### Performance Metrics

#### Download Speed
```bash
psql -U postgres -d filings_db -c "
SELECT
    DATE(er.started_at) as date,
    COUNT(DISTINCT f.id) as filings_processed,
    COUNT(a.id) as artifacts_downloaded,
    ROUND(er.duration_seconds / 3600.0, 2) as hours,
    ROUND(COUNT(a.id) / (er.duration_seconds / 3600.0), 0) as artifacts_per_hour
FROM execution_runs er
LEFT JOIN filings f ON DATE(f.created_at) = DATE(er.started_at)
LEFT JOIN artifacts a ON a.filing_id = f.id AND a.status = 'downloaded'
WHERE er.run_type = 'incremental'
GROUP BY DATE(er.started_at), er.duration_seconds
ORDER BY date DESC
LIMIT 10;
"
```

#### SLA Compliance
```bash
psql -U postgres -d filings_db -c "
SELECT
    DATE(er.started_at) as date,
    COUNT(*) as total_runs,
    SUM(CASE WHEN iu.sla_met THEN 1 ELSE 0 END) as sla_compliant,
    ROUND(AVG(iu.success_rate), 2) as avg_success_rate,
    ROUND(AVG(er.duration_seconds / 3600.0), 2) as avg_hours
FROM execution_runs er
JOIN incremental_updates iu ON iu.execution_run_id = er.id
WHERE er.run_type = 'incremental'
GROUP BY DATE(er.started_at)
ORDER BY date DESC
LIMIT 30;
"
```

### Health Checks

#### System Health Dashboard
Create this SQL query to run regularly:
```sql
-- System Health Dashboard
WITH stats AS (
    SELECT
        COUNT(*) FILTER (WHERE exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')) as target_companies,
        COUNT(*) as total_companies
    FROM companies
),
filing_stats AS (
    SELECT
        COUNT(*) as total_filings,
        COUNT(DISTINCT company_id) as companies_with_filings
    FROM filings
),
artifact_stats AS (
    SELECT
        status,
        COUNT(*) as count
    FROM artifacts
    GROUP BY status
),
latest_run AS (
    SELECT
        run_type,
        started_at,
        ROUND(duration_seconds / 3600.0, 2) as hours
    FROM execution_runs
    ORDER BY started_at DESC
    LIMIT 1
)
SELECT
    'Companies' as metric,
    s.target_companies::text || ' target / ' || s.total_companies::text || ' total' as value
FROM stats s
UNION ALL
SELECT
    'Filings',
    fs.total_filings::text || ' total, ' || fs.companies_with_filings::text || ' companies'
FROM filing_stats fs
UNION ALL
SELECT
    'Artifacts - ' || status,
    count::text
FROM artifact_stats
UNION ALL
SELECT
    'Last Run',
    run_type || ' at ' || started_at::text || ' (' || hours::text || ' hours)'
FROM latest_run;
```

#### Storage Usage
```bash
# Check disk usage
du -sh /data/filings

# More detailed breakdown
du -h --max-depth=2 /data/filings | sort -hr | head -20

# Check database size
psql -U postgres -d filings_db -c "
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

### Log Analysis

#### View Recent Logs
```bash
# If using structured JSON logs
tail -100 logs/filings-etl.log | jq '.'

# Filter for errors
tail -1000 logs/filings-etl.log | jq 'select(.level == "error")'

# Count by log level
tail -1000 logs/filings-etl.log | jq -r '.level' | sort | uniq -c
```

---

## Troubleshooting

### Common Issues and Solutions

#### Issue 1: SEC_USER_AGENT Error
**Error Message**:
```
ValidationError: SEC_USER_AGENT must be customized with your company name and email
```

**Solution**:
1. Edit `.env` file:
```bash
nano .env
```
2. Change the SEC_USER_AGENT line:
```bash
SEC_USER_AGENT=YourCompanyName contact@yourcompany.com
```
3. Save and retry

#### Issue 2: Database Connection Failed
**Error Message**:
```
psycopg.OperationalError: connection to server failed
```

**Solution**:
```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# If not running, start it
docker-compose up -d postgres

# Or if using local PostgreSQL
sudo systemctl start postgresql  # Linux
brew services start postgresql   # macOS

# Verify connection
psql -U postgres -d filings_db -c "SELECT 1;"
```

#### Issue 3: Rate Limit 429 Errors
**Error Message**:
```
HTTP 429: Too Many Requests
```

**Solution**:
The system automatically handles rate limiting and retries. However, if you see many 429 errors:

1. Check your SEC_RATE_LIMIT setting:
```bash
grep SEC_RATE_LIMIT .env
# Should be 10 (SEC allows 10 req/sec)
```

2. Ensure User-Agent is properly set (see Issue 1)

3. Wait a few minutes and retry - the exponential backoff will handle it

#### Issue 4: Disk Space Full
**Error Message**:
```
OSError: [Errno 28] No space left on device
```

**Solution**:
```bash
# Check available space
df -h /data/filings

# Clean up old or test data
rm -rf /data/filings/test_*

# Consider moving to larger storage
# Update STORAGE_ROOT in .env
STORAGE_ROOT=/mnt/larger-drive/filings
```

#### Issue 5: Download Failures
**Error Message**:
```
Failed to download artifact: Connection timeout
```

**Solution**:
```bash
# 1. Check network connectivity
curl -I https://www.sec.gov

# 2. View failed artifacts
psql -U postgres -d filings_db -c "
SELECT COUNT(*) FROM artifacts WHERE status = 'failed';
"

# 3. Check error details
psql -U postgres -d filings_db -c "
SELECT error_message, COUNT(*)
FROM artifacts
WHERE status = 'failed'
GROUP BY error_message;
"

# 4. Re-run incremental (will retry failures)
python main.py incremental
```

#### Issue 6: Missing XBRL Files
**Symptom**: HTML files downloaded but no XBRL files

**Explanation**: Not all filings have XBRL data. This is normal.

**Verify**:
```bash
psql -U postgres -d filings_db -c "
SELECT
    artifact_type,
    COUNT(*) as count
FROM artifacts
WHERE status = 'downloaded'
GROUP BY artifact_type;
"
```

#### Issue 7: Amendment vs Original Filing
**Question**: Why do I see multiple filings with similar dates?

**Explanation**: Companies file amendments (form_type ending in `/A`). Both original and amendments are stored.

**Query to see amendments**:
```bash
psql -U postgres -d filings_db -c "
SELECT
    c.ticker,
    f.form_type,
    f.filing_date,
    f.amends_accession
FROM filings f
JOIN companies c ON f.company_id = c.id
WHERE f.form_type LIKE '%/A'
ORDER BY f.filing_date DESC
LIMIT 10;
"
```

### Debug Mode

#### Enable Detailed Logging
```bash
# Temporary (for one run)
LOG_LEVEL=DEBUG python main.py incremental

# Permanent (edit .env)
echo "LOG_LEVEL=DEBUG" >> .env
```

#### Test Individual Components
```bash
# Test SEC API
python -c "
from services.sec_api import SECAPIClient
client = SECAPIClient()
tickers = client.get_company_tickers()
print(f'Fetched {len(tickers)} companies')
"

# Test database connection
python -c "
from config.db import get_db_session
from models import Company
with get_db_session() as session:
    count = session.query(Company).count()
    print(f'Database has {count} companies')
"

# Test storage
python -c "
from services.storage import get_storage_adapter
storage = get_storage_adapter()
test_path = 'test/file.txt'
storage.write(test_path, b'Hello, World!')
content = storage.read(test_path)
print(f'Storage test: {content.decode()}')
storage.delete(test_path)
"
```

---

## Best Practices

### Production Deployment

#### 1. Use Docker for PostgreSQL
```yaml
# docker-compose.yml (already provided)
services:
  postgres:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
```

Benefits:
- Easy setup and teardown
- Isolated environment
- Consistent across machines
- Simple backup with volume snapshots

#### 2. Secure Your Credentials
```bash
# Never commit .env file
echo ".env" >> .gitignore

# Use strong passwords
# In .env:
DB_PASSWORD=$(openssl rand -base64 32)

# Restrict file permissions
chmod 600 .env
```

#### 3. Set Up Monitoring Alerts
Create a monitoring script (`monitor.sh`):
```bash
#!/bin/bash
# Check SLA compliance
SLA_FAILED=$(psql -U postgres -d filings_db -t -c "
SELECT COUNT(*) FROM incremental_updates
WHERE sla_met = false
  AND created_at > NOW() - INTERVAL '1 day';
")

if [ "$SLA_FAILED" -gt 0 ]; then
    echo "ALERT: SLA violation detected!"
    # Send email or Slack notification
fi
```

#### 4. Regular Backups
```bash
# Daily database backup
#!/bin/bash
BACKUP_DIR="/backups/filings"
DATE=$(date +%Y%m%d)

# Backup database
pg_dump -U postgres filings_db | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Backup files (incremental)
rsync -av --link-dest="$BACKUP_DIR/latest" /data/filings "$BACKUP_DIR/$DATE"
ln -nsf "$BACKUP_DIR/$DATE" "$BACKUP_DIR/latest"

# Clean old backups (keep 30 days)
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +30 -delete
```

Add to crontab:
```bash
0 3 * * * /path/to/backup.sh >> /var/log/filings-backup.log 2>&1
```

#### 5. Resource Limits
Configure optimal settings in `.env`:
```bash
# For 8 GB RAM system
MAX_WORKERS=10

# For 16 GB RAM system
MAX_WORKERS=20

# For slower networks
SEC_TIMEOUT=60
```

#### 6. Staging Environment
Test updates in staging before production:
```bash
# Staging .env
DB_NAME=filings_db_staging
STORAGE_ROOT=/data/filings-staging

# Run backfill with limit
python main.py backfill --limit 100

# Verify everything works
python run_tests.py
```

### Data Quality

#### 1. Verify Downloads
```bash
# Check for missing images in HTML
psql -U postgres -d filings_db -c "
SELECT
    c.ticker,
    f.accession_number,
    COUNT(*) FILTER (WHERE a.artifact_type = 'html') as html_count,
    COUNT(*) FILTER (WHERE a.artifact_type = 'image') as image_count
FROM artifacts a
JOIN filings f ON a.filing_id = f.id
JOIN companies c ON f.company_id = c.id
WHERE a.status = 'downloaded'
GROUP BY c.ticker, f.accession_number
HAVING COUNT(*) FILTER (WHERE a.artifact_type = 'html') > 0
ORDER BY image_count DESC
LIMIT 20;
"
```

#### 2. Validate File Integrity
```bash
# Check for duplicate SHA256 hashes (should be unique)
psql -U postgres -d filings_db -c "
SELECT sha256, COUNT(*)
FROM artifacts
WHERE sha256 IS NOT NULL
GROUP BY sha256
HAVING COUNT(*) > 1;
"
# Should return no rows
```

#### 3. Monitor Error Rates
```bash
# Weekly error report
psql -U postgres -d filings_db -c "
SELECT
    DATE_TRUNC('week', occurred_at) as week,
    error_type,
    COUNT(*) as error_count
FROM error_logs
WHERE occurred_at > NOW() - INTERVAL '30 days'
GROUP BY week, error_type
ORDER BY week DESC, error_count DESC;
"
```

### Performance Optimization

#### 1. Tune PostgreSQL
Add to `postgresql.conf`:
```
# Increase shared buffers
shared_buffers = 2GB

# Increase work memory
work_mem = 64MB

# Increase maintenance work memory
maintenance_work_mem = 512MB

# Increase checkpoint timeout
checkpoint_timeout = 15min
```

#### 2. Optimize Network
```bash
# Use compression for XBRL files
# The system handles this automatically

# Consider running on cloud with fast SEC connectivity
# AWS us-east-1 recommended (close to SEC servers)
```

#### 3. Parallel Processing
```bash
# Increase workers for faster downloads
MAX_WORKERS=20  # In .env

# But stay within rate limits
# 10 req/sec SEC limit is enforced per client
```

---

## FAQ

### General Questions

**Q: How long does the initial backfill take?**
A: For all ~6,000 companies (2023-2025), expect 8-24 hours depending on:
- Network speed
- Number of workers
- SEC server response times

**Q: How much storage do I need?**
A: Approximately:
- 500 GB for complete dataset (HTML + images + XBRL)
- 100 GB minimum for testing
- Plan for 20% growth per year

**Q: Can I run this on Windows?**
A: Yes, but WSL (Windows Subsystem for Linux) is recommended for best compatibility. Native Windows support is possible but not as well tested.

**Q: Is this legal to use?**
A: Yes! The SEC provides this data publicly and encourages responsible use. Just ensure you:
- Use a proper User-Agent with contact info
- Respect rate limits (10 req/sec)
- Don't resell raw SEC data

**Q: Can I use this for commercial purposes?**
A: Yes, the project is MIT licensed. However, check SEC terms for data usage restrictions.

### Technical Questions

**Q: Why store all 13,000 companies if we only target 6,000?**
A: For flexibility and data completeness. Companies can change exchanges, and having the full dataset allows for:
- Expanding scope later
- Historical analysis
- Audit trail

**Q: How do I handle amendments?**
A: Amendments are stored separately with `amends_accession` linking to original. To get latest version:
```sql
SELECT * FROM filings
WHERE company_id = X
ORDER BY filing_date DESC, amends_accession NULLS FIRST
LIMIT 1;
```

**Q: Can I migrate to S3?**
A: Yes! The system is designed for S3 migration:
1. Implement `S3Adapter` in `services/storage.py`
2. Set `STORAGE_BACKEND=s3` in `.env`
3. No other code changes needed

**Q: What if I miss a week of incremental updates?**
A: The system scans the last 7 days. If you miss more than 7 days:
1. Increase `INCREMENTAL_LOOKBACK_DAYS` in `.env`
2. Run incremental update
3. Or run full backfill (it's idempotent)

**Q: How do I process only specific companies?**
A: Modify the backfill query to filter by ticker:
```python
# In jobs/backfill.py
target_tickers = ['AAPL', 'MSFT', 'GOOGL']
companies = session.query(Company).filter(
    Company.ticker.in_(target_tickers)
).all()
```

**Q: Can I run multiple instances in parallel?**
A: Yes, but be careful:
- Use different databases (DB_NAME)
- Use different storage paths (STORAGE_ROOT)
- Stay within SEC rate limits globally (10 req/sec per IP)

### Troubleshooting Questions

**Q: Why are some artifacts marked as 'not_available'?**
A: This means the SEC doesn't have the file. Reasons:
- Filing is too old (pre-EDGAR)
- File was removed by SEC
- Filing was withdrawn
This is normal and expected.

**Q: Why do I see 'UNKNOWN' exchange for some companies?**
A: These companies are SEC-registered but not on NASDAQ/NYSE. They might be:
- OTC (over-the-counter) stocks
- Pink sheets
- Recently delisted
- International companies

**Q: How do I re-download a specific filing?**
A:
```bash
# 1. Find the filing
psql -U postgres -d filings_db -c "
SELECT id FROM filings WHERE accession_number = 'ACCESSION_NUMBER';
"

# 2. Reset artifacts
psql -U postgres -d filings_db -c "
UPDATE artifacts
SET status = 'pending_download', retry_count = 0
WHERE filing_id = FILING_ID;
"

# 3. Run incremental
python main.py incremental
```

**Q: What if the ETL crashes mid-run?**
A: The system is designed for crash recovery:
- All operations are idempotent
- Database uses transactions
- Simply re-run the same command
- It will resume from where it left off

---

## Next Steps

### After Setup

1. **Run Initial Backfill**
   ```bash
   python main.py listings
   python main.py listings-ref-sync
   python main.py exchange-enrichment
   python main.py backfill --limit 10  # Test first
   python main.py backfill  # Full run when ready
   ```

2. **Set Up Automated Updates**
   ```bash
   crontab -e
   # Add: 0 2 * * 1 cd /path/to/filings-etl && /path/to/venv/bin/python main.py incremental
   ```

3. **Configure Monitoring**
   - Set up health check scripts
   - Configure alerts for SLA violations
   - Set up log aggregation

4. **Plan for Growth**
   - Monitor storage usage
   - Plan database scaling
   - Consider S3 migration for cloud

### Learning Resources

- **SEC EDGAR Documentation**: https://www.sec.gov/edgar
- **SEC Rate Limits**: https://www.sec.gov/os/accessing-edgar-data
- **PostgreSQL Docs**: https://www.postgresql.org/docs/
- **SQLAlchemy ORM**: https://docs.sqlalchemy.org/

### Getting Help

1. Check this user guide
2. Review TROUBLESHOOTING_CN.md
3. Check error_logs table in database
4. Enable DEBUG logging
5. Review code documentation in source files

---

## Conclusion

You now have everything you need to operate the US-Listed Filings ETL system effectively. Remember:

- Start small (test with --limit)
- Monitor regularly (SLA metrics)
- Back up frequently (database + files)
- Stay compliant (User-Agent, rate limits)

Happy data collecting!

---

**Document Version**: 1.0
**Last Updated**: 2025-10-29
**Project**: US-Listed Filings ETL System
