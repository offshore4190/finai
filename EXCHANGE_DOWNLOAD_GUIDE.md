# Exchange Download Guide

Complete guide for downloading filings from all exchanges (NASDAQ, NYSE, and more).

## Overview

This system provides three main scripts for downloading SEC filings:

1. **`nyse_full_backfill.py`** - Download all NYSE company filings (2,353 companies)
2. **`nasdaq_full_backfill.py`** - Download all NASDAQ company filings (4,091 companies)
3. **`all_exchanges_backfill.py`** - Download filings from all exchanges (unified script)
4. **`monitor_backfill_progress.py`** - Real-time progress monitoring

## Quick Start

### 1. Download NYSE Filings (Fastest Method)

```bash
# Activate virtual environment
source venv/bin/activate

# Full backfill: discover + download
python nyse_full_backfill.py

# Or run in phases:
python nyse_full_backfill.py --discover-only   # Phase 1: Discovery
python nyse_full_backfill.py --download-only   # Phase 2: Download
```

### 2. Download NASDAQ Filings

```bash
source venv/bin/activate
python nasdaq_full_backfill.py
```

### 3. Download All Exchanges

```bash
source venv/bin/activate

# All exchanges
python all_exchanges_backfill.py

# Specific exchange
python all_exchanges_backfill.py --exchange NYSE
python all_exchanges_backfill.py --exchange NASDAQ
```

### 4. Monitor Progress

```bash
# Real-time monitoring (refreshes every 30 seconds)
python monitor_backfill_progress.py

# Single snapshot
python monitor_backfill_progress.py --once

# Custom refresh interval (in seconds)
python monitor_backfill_progress.py --interval 60
```

## Performance Metrics

### Expected Processing Times

Based on current data and SEC rate limits (10 requests/second):

#### NYSE (2,353 companies)
- **Discovery Phase**: ~4-5 hours
  - API requests: ~2,353 companies × 1 request each
  - Estimated filings: ~25,000-30,000 filings (10-12 per company avg)

- **Download Phase**: Variable based on file sizes
  - Typical range: 3-8 hours depending on document sizes

- **Total Time**: ~8-12 hours

#### NASDAQ (4,091 companies)
- **Discovery Phase**: ~7-8 hours
  - API requests: ~4,091 companies × 1 request each
  - Estimated filings: ~45,000-50,000 filings

- **Download Phase**: Variable based on file sizes
  - Typical range: 6-12 hours

- **Total Time**: ~14-20 hours

#### All Exchanges (17,003+ companies)
- **Discovery Phase**: ~28-30 hours
- **Download Phase**: ~24-48 hours
- **Total Time**: ~3-4 days

### Rate Limiting

All scripts respect SEC's rate limit of **10 requests per second**:
- Minimum interval: 100ms between requests
- Automatic retry with exponential backoff
- User-Agent header: Your email from .env

## Script Details

### NYSE Full Backfill (`nyse_full_backfill.py`)

**What it does:**
1. Queries all NYSE companies from the database (2,353 companies)
2. Fetches filing metadata from SEC for each company
3. Filters for 10-K and 10-Q forms from 2023-2025
4. Creates filing records and artifact entries
5. Downloads all HTML documents to local storage

**Usage:**
```bash
# Full pipeline
python nyse_full_backfill.py

# Discovery only (creates filing records, no downloads)
python nyse_full_backfill.py --discover-only

# Download only (downloads pending artifacts)
python nyse_full_backfill.py --download-only
```

**Output:**
- Progress logs every 100 companies during discovery
- Download progress every 100 artifacts
- Final summary with counts and success rates

### NASDAQ Full Backfill (`nasdaq_full_backfill.py`)

Same functionality as NYSE script but for NASDAQ exchange.

### All Exchanges Backfill (`all_exchanges_backfill.py`)

**Advanced features:**
- Unified script for all exchanges
- Exchange-specific statistics tracking
- Progress checkpoints every 50 companies
- Detailed per-exchange metrics

**Usage:**
```bash
# All exchanges
python all_exchanges_backfill.py

# Specific exchange
python all_exchanges_backfill.py --exchange NYSE
python all_exchanges_backfill.py --exchange NASDAQ

# Phased execution
python all_exchanges_backfill.py --discover-only --exchange NYSE
python all_exchanges_backfill.py --download-only --exchange NYSE
```

### Progress Monitor (`monitor_backfill_progress.py`)

**Features:**
- Real-time statistics for all exchanges
- Filing discovery counts
- Download progress with percentages
- Recent activity tracking (last 5 minutes)
- Delta tracking between refreshes

**Output Example:**
```
================================================================================
BACKFILL PROGRESS MONITOR - 2025-10-29 23:00:17
================================================================================

COMPANIES:
  Total:  17,003
  NASDAQ: 4,091
  NYSE:   2,353

FILINGS DISCOVERED:
  Total:  26,453
  NASDAQ: 26,317
  NYSE:   135

NASDAQ DOWNLOADS:
  Downloaded: 333/26,616 (1.3%)
  Pending:    26,283

NYSE DOWNLOADS:
  Downloaded: 29/141 (20.6%)
  Pending:    112

OVERALL DOWNLOADS:
  Downloaded: 362/26,758 (1.4%)
  Pending:    26,396
  Failed:     6
```

## Running in Background

### Using tmux (Recommended)

```bash
# Start new tmux session
tmux new -s nyse_backfill

# Run the script
source venv/bin/activate
python nyse_full_backfill.py

# Detach: Press Ctrl+B, then D
# Reattach: tmux attach -t nyse_backfill
```

### Using screen

```bash
# Start new screen session
screen -S nyse_backfill

# Run the script
source venv/bin/activate
python nyse_full_backfill.py

# Detach: Press Ctrl+A, then D
# Reattach: screen -r nyse_backfill
```

### Using nohup

```bash
source venv/bin/activate
nohup python nyse_full_backfill.py > nyse_backfill.log 2>&1 &

# Check progress
tail -f nyse_backfill.log

# Find process
ps aux | grep nyse_full_backfill
```

## Monitoring Multiple Sessions

Run downloads and monitoring in parallel:

```bash
# Terminal 1: Run NYSE backfill
tmux new -s nyse
source venv/bin/activate
python nyse_full_backfill.py

# Terminal 2: Run NASDAQ backfill
tmux new -s nasdaq
source venv/bin/activate
python nasdaq_full_backfill.py

# Terminal 3: Monitor progress
tmux new -s monitor
source venv/bin/activate
python monitor_backfill_progress.py --interval 30
```

## Parallel Downloads Strategy

For fastest results, run both exchanges in parallel:

```bash
# Terminal 1: NYSE
python nyse_full_backfill.py

# Terminal 2: NASDAQ
python nasdaq_full_backfill.py

# Terminal 3: Monitor
python monitor_backfill_progress.py
```

**Note**: Each script has its own rate limiter, but they share the same SEC endpoint. Combined rate is still ~10 req/sec total.

## Resume After Interruption

All scripts are **resumable**:

- Discovery phase: Skips existing filings (checks by accession_number)
- Download phase: Only processes artifacts with status='pending_download'

Simply re-run the same command to resume:

```bash
# If interrupted, just run again
python nyse_full_backfill.py
```

## Troubleshooting

### Script Stopped or Failed

```bash
# Check what's pending
python monitor_backfill_progress.py --once

# Resume discovery
python nyse_full_backfill.py --discover-only

# Resume downloads
python nyse_full_backfill.py --download-only
```

### Check Failed Downloads

```bash
python -c "
from config.db import get_db_session
from models import Artifact

with get_db_session() as session:
    failed = session.query(Artifact).filter(
        Artifact.status == 'failed'
    ).count()
    print(f'Failed artifacts: {failed}')
"
```

### Retry Failed Downloads

Failed downloads are automatically retried up to 3 times. To manually retry:

```bash
# Set failed artifacts back to pending
python -c "
from config.db import get_db_session
from models import Artifact

with get_db_session() as session:
    artifacts = session.query(Artifact).filter(
        Artifact.status == 'failed'
    ).all()

    for artifact in artifacts:
        artifact.status = 'pending_download'
        artifact.retry_count = 0

    session.commit()
    print(f'Reset {len(artifacts)} failed artifacts')
"

# Then run download
python nyse_full_backfill.py --download-only
```

## Database Queries

### Check Progress by Exchange

```bash
source venv/bin/activate
python -c "
from config.db import get_db_session
from models import Company, Filing, Artifact

with get_db_session() as session:
    # NYSE stats
    nyse_companies = session.query(Company).filter(Company.exchange == 'NYSE').count()
    nyse_filings = session.query(Filing).join(Company).filter(Company.exchange == 'NYSE').count()
    nyse_downloaded = session.query(Artifact).join(Filing).join(Company).filter(
        Company.exchange == 'NYSE',
        Artifact.status == 'downloaded'
    ).count()
    nyse_pending = session.query(Artifact).join(Filing).join(Company).filter(
        Company.exchange == 'NYSE',
        Artifact.status == 'pending_download'
    ).count()

    print(f'NYSE:')
    print(f'  Companies: {nyse_companies}')
    print(f'  Filings: {nyse_filings}')
    print(f'  Downloaded: {nyse_downloaded}')
    print(f'  Pending: {nyse_pending}')
"
```

## Best Practices

1. **Use tmux/screen**: Always run long operations in a persistent session
2. **Monitor progress**: Keep the monitor running in a separate terminal
3. **Phased execution**: Run discovery first, verify counts, then download
4. **Check logs**: Review structured logs for any errors or warnings
5. **Verify storage**: Ensure sufficient disk space before starting
6. **Database backups**: Backup database before major operations

## Storage Requirements

Estimated storage per filing type:
- 10-K HTML: 200KB - 2MB (avg ~500KB)
- 10-Q HTML: 100KB - 1MB (avg ~300KB)

### NYSE Estimates (2,353 companies)
- ~25,000-30,000 filings
- ~10-15 GB total storage

### NASDAQ Estimates (4,091 companies)
- ~45,000-50,000 filings
- ~18-25 GB total storage

### All Exchanges (17,003+ companies)
- ~180,000-200,000 filings
- ~70-90 GB total storage

## Advanced Options

### Custom Date Range

To modify the date range, edit the script and change:

```python
# Filter for 2023-2025
if filing_date.year < 2023:
    continue
```

To:
```python
# Filter for your desired range
if filing_date.year < 2020 or filing_date.year > 2025:
    continue
```

### Custom Form Types

To include additional form types (e.g., 8-K, 10-K/A):

```python
# Current filter
if form_type not in ['10-K', '10-Q']:
    continue
```

To:
```python
# Expanded filter
if form_type not in ['10-K', '10-Q', '8-K', '10-K/A', '10-Q/A']:
    continue
```

## Summary

**Fast & Accurate NYSE Downloads:**

```bash
# Recommended workflow
source venv/bin/activate

# Terminal 1: Start NYSE download
tmux new -s nyse
python nyse_full_backfill.py

# Terminal 2: Monitor progress
tmux new -s monitor
python monitor_backfill_progress.py

# Check status anytime
python monitor_backfill_progress.py --once
```

Expected completion time: **8-12 hours** for all NYSE filings.
