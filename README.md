# US-Listed Filings Full DB Builder

A production-ready ETL system for building a complete database of SEC 10-K and 10-Q filings for all SEC-listed companies (2023-2025), with exchange enrichment to focus on NASDAQ and NYSE companies, weekly incremental updates, and robust error handling.

## Features

- ✅ **Comprehensive Coverage**: All NASDAQ + NYSE companies (~6,000)
- ✅ **Complete Artifacts**: HTML (with localized images) + XBRL + metadata
- ✅ **Weekly Incremental Updates**: Scans last 7 days for new filings
- ✅ **Idempotent Operations**: Skip already-downloaded files via SHA256 deduplication
- ✅ **Robust Retry Logic**: Exponential backoff with max 3 retries per artifact
- ✅ **SLA Monitoring**: ≤6 hours per incremental run, ≥99% success rate
- ✅ **Cloud-Ready Design**: Easy migration to S3 storage
- ✅ **SEC Compliant**: Rate limiting (10 req/sec) + proper User-Agent

## Ingestion Strategy: Full 13k + Downstream Filtering

This system follows a **"full ingestion, downstream filtering"** approach:

### Why Ingest All ~13,000 SEC Filers?

1. **Data Completeness**: SEC's company tickers API returns all filers (~13k) without exchange metadata
2. **No False Negatives**: Companies can delist/relist, change exchanges, or have complex structures
3. **Future Flexibility**: Full dataset available for expanded scope (e.g., adding Russell 2000, adding S&P indices)
4. **Audit Trail**: Complete record of all SEC filers for compliance and research

### How We Filter to Target ~6k Companies

1. **Listings Build** (`python main.py listings`):
   - Ingests all ~13k companies from SEC API
   - Initially sets `exchange = 'UNKNOWN'` for all

2. **Exchange Reference Sync** (`python main.py listings-ref-sync`):
   - Downloads NASDAQ and NYSE official listing files
   - Populates `listings_ref` table with authoritative exchange mappings
   - Includes ETF flags for accurate filtering

3. **Exchange Enrichment** (`python main.py exchange-enrichment`):
   - Joins company tickers with `listings_ref` data
   - Updates `exchange` field: `UNKNOWN` → `NASDAQ`, `NYSE`, `NYSE American`, `NYSE Arca`
   - Prefers non-ETF when symbol conflicts exist
   - Result: ~6k companies with proper exchange assignments

4. **Downstream Filtering**:
   - View `v_target_companies` filters to target exchanges (excludes UNKNOWN and ETFs)
   - Backfill and incremental jobs read from filtered view
   - **Important**: Filing uniqueness (`UNIQUE(accession_number)`) remains unchanged
   - **Important**: All 13k companies remain in database for audit/flexibility

### Workflow

```
Listings Build → Listings Ref Sync → Exchange Enrichment → Backfill/Incremental
(ingest 13k)     (get NASDAQ/NYSE)   (enrich exchanges)    (process ~6k)
```

**Typical setup sequence:**
```bash
python main.py listings                # Ingest all 13k SEC filers
python main.py listings-ref-sync       # Sync NASDAQ/NYSE reference data
python main.py exchange-enrichment     # Enrich company exchanges
python main.py backfill --limit 10     # Test with 10 companies
python main.py backfill                # Full backfill of ~6k target companies
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Listings Build │────▶│    Backfill     │────▶│   Incremental   │
│  (One-time)     │     │  (One-time)     │     │    (Weekly)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                        │
         ▼                       ▼                        ▼
    ┌────────────────────────────────────────────────────────┐
    │              SEC EDGAR API (Rate Limited)              │
    └────────────────────────────────────────────────────────┘
         │                       │                        │
         ▼                       ▼                        ▼
    ┌────────────┐         ┌──────────┐          ┌──────────────┐
    │ PostgreSQL │         │ Storage  │          │ Retry Queue  │
    │  Metadata  │         │  Layer   │          │   + Logs     │
    └────────────┘         └──────────┘          └──────────────┘
```

## Database Schema

- **companies**: Ticker-to-CIK mappings (all ~13k SEC filers)
- **listings_ref**: NASDAQ/NYSE exchange reference data (for enrichment)
- **filings**: SEC filing metadata (10-K, 10-Q, amendments)
- **artifacts**: Download tracking with SHA256 integrity
- **retry_queue**: Failed artifacts with scheduled retries
- **execution_runs**: Audit trail for all ETL runs
- **incremental_updates**: Weekly SLA metrics
- **error_logs**: Detailed failure forensics
- **v_target_companies** (view): Filtered ~6k companies (NASDAQ/NYSE family, no ETFs)

## Storage Layout

```
/data/filings/
├── NASDAQ/
│   └── AAPL/
│       └── 2023/
│           ├── AAPL_2023_Q1_03-02-2023.html
│           ├── AAPL_2023_Q1_03-02-2023_image01.png
│           ├── AAPL_2023_Q1_03-02-2023_image02.png
│           └── xbrl/
│               ├── aapl-20230930.xsd
│               └── aapl-20230930_cal.xml
└── NYSE/
    └── JPM/
        └── 2024/
            └── ...
```

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- 500GB+ storage (for full dataset)

### Installation

1. **Clone and setup**:
```bash
cd filings-etl
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env and set SEC_USER_AGENT (REQUIRED!)
nano .env
```

**CRITICAL**: Update `SEC_USER_AGENT` in `.env`:
```
SEC_USER_AGENT=YourCompany contact@yourcompany.com
```

3. **Initialize database**:
```bash
# Start PostgreSQL (or use Docker Compose)
docker-compose up -d postgres

# Create schema
python main.py init-db
```

### Usage

#### 1. Build Company Listings
```bash
python main.py listings
```
Fetches all ~13k SEC filers from SEC API and populates `companies` table with `exchange='UNKNOWN'`.

#### 2. Sync Exchange Reference Data
```bash
python main.py listings-ref-sync
```
Downloads NASDAQ and NYSE official listing files and populates `listings_ref` table. This provides authoritative exchange mappings and ETF flags.

#### 3. Enrich Company Exchanges
```bash
python main.py exchange-enrichment
```
Joins company tickers with `listings_ref` data and updates `companies.exchange` from `UNKNOWN` to proper values (`NASDAQ`, `NYSE`, `NYSE American`, `NYSE Arca`). After this step, ~6k companies will have proper exchange assignments.

#### 4. Backfill Historical Filings
```bash
# Full backfill (all companies)
python main.py backfill

# Limited backfill for testing
python main.py backfill --limit 10
```
Discovers all 10-K/10-Q filings from 2023-2025 for target companies (~6k) and creates artifact records. **Note**: Only processes companies with `exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')`.

#### 5. Run Incremental Update
```bash
python main.py incremental
```
Scans last 7 days for new filings, downloads artifacts, and retries failures.

**Schedule with cron** (every Monday at 2 AM):
```bash
0 2 * * 1 cd /path/to/filings-etl && /path/to/venv/bin/python main.py incremental >> logs/incremental.log 2>&1
```

## Docker Deployment

### Using Docker Compose

```bash
# Start services
docker-compose up -d

# Initialize database
docker-compose exec etl python main.py init-db

# Run listings
docker-compose exec etl python main.py listings

# Run backfill
docker-compose exec etl python main.py backfill

# Run incremental
docker-compose exec etl python main.py incremental

# View logs
docker-compose logs -f etl
```

### Production Deployment

1. **Update `.env` for production**:
```bash
DB_HOST=prod-postgres.example.com
STORAGE_ROOT=/mnt/filings-prod
SEC_USER_AGENT=YourCompany legal@yourcompany.com
LOG_FORMAT=json
```

2. **Build and deploy**:
```bash
docker build -t filings-etl:latest .
docker push your-registry/filings-etl:latest
```

3. **Setup cron in container** or use orchestrator (Kubernetes CronJob, AWS ECS Scheduled Tasks, etc.)

## Configuration

All settings are in `config/settings.py` and can be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | localhost | PostgreSQL host |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_NAME` | filings_db | Database name |
| `STORAGE_ROOT` | /data/filings | Storage directory |
| `SEC_USER_AGENT` | **REQUIRED** | User-Agent for SEC (must include email) |
| `SEC_RATE_LIMIT` | 10 | Requests per second to SEC |
| `MAX_WORKERS` | 10 | Concurrent download threads |
| `INCREMENTAL_LOOKBACK_DAYS` | 7 | Days to scan for new filings |
| `SLA_DURATION_HOURS` | 6 | Max hours for incremental run |
| `SLA_SUCCESS_RATE` | 99.0 | Minimum success rate (%) |

## SLA Monitoring

### Check Last Incremental Run
```sql
SELECT 
    er.started_at,
    er.duration_seconds / 3600.0 AS duration_hours,
    iu.success_rate,
    iu.sla_met,
    iu.new_filings_found
FROM execution_runs er
JOIN incremental_updates iu ON iu.execution_run_id = er.id
WHERE er.run_type = 'incremental'
ORDER BY er.started_at DESC
LIMIT 1;
```

### SLA Violations
```sql
SELECT 
    started_at,
    duration_seconds,
    artifacts_succeeded,
    artifacts_failed
FROM execution_runs er
JOIN incremental_updates iu ON iu.execution_run_id = er.id
WHERE iu.sla_met = false
ORDER BY started_at DESC;
```

### Failed Artifacts Requiring Manual Review
```sql
SELECT 
    c.ticker,
    f.accession_number,
    a.artifact_type,
    a.retry_count,
    a.error_message
FROM artifacts a
JOIN filings f ON a.filing_id = f.id
JOIN companies c ON f.company_id = c.id
WHERE a.status = 'failed' 
  AND a.retry_count >= 3
ORDER BY a.last_attempt_at DESC;
```

## Cloud Migration (S3)

The system is designed for easy migration to S3:

1. **Update configuration**:
```bash
STORAGE_BACKEND=s3
S3_BUCKET=filings-prod
S3_REGION=us-east-1
```

2. **Implement S3Adapter** in `services/storage.py`:
```python
class S3Adapter(StorageAdapter):
    def __init__(self, bucket: str, region: str):
        import boto3
        self.s3 = boto3.client('s3', region_name=region)
        self.bucket = bucket
    
    def write(self, path: str, content: bytes) -> bool:
        self.s3.put_object(Bucket=self.bucket, Key=path, Body=content)
        return True
    # ... implement other methods
```

3. **Enable S3 versioning** for amendments

## Testing

```bash
# Run unit tests
pytest tests/unit/

# Run integration tests (requires PostgreSQL)
pytest tests/integration/

# Test with limited dataset
python main.py backfill --limit 5
python main.py incremental
```

## Troubleshooting

### SEC Rate Limiting (429 errors)
- Ensure `SEC_USER_AGENT` is properly set
- Check `SEC_RATE_LIMIT` setting (default 10 req/sec)
- System automatically retries with exponential backoff

### Failed Downloads
- Check `error_logs` table for details
- Artifacts auto-retry up to 3 times
- After 3 failures, manual review required

### SLA Violations
- Check `incremental_updates.sla_met` column
- Review `execution_runs.duration_seconds`
- Increase `MAX_WORKERS` if bottleneck is downloads
- Check network connectivity to SEC

### Database Connection Issues
- Verify PostgreSQL is running
- Check connection settings in `.env`
- Ensure database exists: `createdb filings_db`

## Project Structure

```
filings-etl/
├── config/          # Configuration and database setup
├── models/          # SQLAlchemy ORM models
├── services/        # Core services (SEC API, storage, downloader)
├── jobs/            # ETL job implementations
├── utils/           # Utilities (retry, hashing, rate limiter)
├── migrations/      # Database schema
├── tests/           # Test suite
├── main.py          # CLI entry point
├── requirements.txt # Python dependencies
└── README.md        # This file
```

## License

MIT License - See LICENSE file for details

## Support

For issues or questions:
1. Check this README and inline code documentation
2. Review `error_logs` table for detailed error information
3. Enable debug logging: `LOG_LEVEL=DEBUG`

## Roadmap

- [ ] Financial field extraction (XBRL parsing)
- [ ] PDF support with OCR
- [ ] Web UI for monitoring
- [ ] Incremental XBRL processing
- [ ] Real-time filing alerts
### Experiment: Version Control
