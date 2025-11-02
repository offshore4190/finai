# Running Parallel Downloads - NASDAQ + NYSE

## 🚀 Current Status

✅ **NASDAQ download is now running in background!**
- Process ID: Check with `ps aux | grep nasdaq_full_backfill`
- Log file: `logs/nasdaq_download.log`
- Expected completion: 2-4 hours

---

## ⚙️ Ensure Optimized Backfill Settings

1. **Lock in optimized worker count (8 concurrent downloads).**
   ```bash
   export DOWNLOAD_WORKERS=8
   ```
   Add the same line to `.env` if you want it to persist across shells.

2. **Confirm the active configuration before kicking off NYSE.**
   ```bash
   source .venv/bin/activate && \
   python -c "from config.settings import settings; print(f'Optimized workers: {settings.download_workers}')"
   ```
   You should see `Optimized workers: 8`. If it prints something else, adjust your environment and re-run the command.

3. **Optional smoke test (recommended after any config change).**
   ```bash
   python nyse_full_backfill.py --download-only --limit 10
   ```
   This validates that the optimized pipeline, retries, and storage paths are behaving as expected before you queue the full job.

---

## 📋 To Run NYSE in Another Terminal

### Method 1: Open New Terminal and Run

**In a NEW terminal window/tab:**

```bash
# 1. Navigate to project directory
cd /Users/hao/Desktop/FINAI/files/filings-etl

# 2. Activate virtual environment and ensure optimized workers
source .venv/bin/activate
export DOWNLOAD_WORKERS=8

# 3. (Optional) Spot-check configuration
python -c "from config.settings import settings; print(f'Optimized workers: {settings.download_workers}')"

# 4. Run NYSE download in background using the optimized backfill
nohup python nyse_full_backfill.py --download-only > logs/nyse_download.log 2>&1 &

# 5. Get the process ID
echo "NYSE download started with PID: $!"

# 6. Monitor progress
tail -f logs/nyse_download.log
```

### Method 2: Run from Current Terminal

```bash
# Quick start NYSE (from current terminal)
source .venv/bin/activate && \
export DOWNLOAD_WORKERS=8 && \
nohup python nyse_full_backfill.py --download-only > logs/nyse_download.log 2>&1 &
echo "NYSE PID: $!"
```

---

## 📊 Monitor Both Downloads

### Check Progress

**Monitor NASDAQ:**
```bash
tail -f logs/nasdaq_download.log
```

**Monitor NYSE:**
```bash
tail -f logs/nyse_download.log
```

**Monitor both side-by-side (split terminal):**
```bash
# Terminal 1
tail -f logs/nasdaq_download.log

# Terminal 2 (new tab/pane)
tail -f logs/nyse_download.log
```

### Quick Status Check

**Check database progress:**
```bash
source .venv/bin/activate && python -c "
from config.db import get_db_session
from models import Artifact, Filing, Company

with get_db_session() as session:
    # NASDAQ stats
    nasdaq_downloaded = session.query(Artifact).join(
        Filing, Artifact.filing_id == Filing.id
    ).join(
        Company, Filing.company_id == Company.id
    ).filter(
        Company.exchange == 'NASDAQ',
        Artifact.status == 'downloaded'
    ).count()

    nasdaq_pending = session.query(Artifact).join(
        Filing, Artifact.filing_id == Filing.id
    ).join(
        Company, Filing.company_id == Company.id
    ).filter(
        Company.exchange == 'NASDAQ',
        Artifact.status == 'pending_download'
    ).count()

    # NYSE stats
    nyse_downloaded = session.query(Artifact).join(
        Filing, Artifact.filing_id == Filing.id
    ).join(
        Company, Filing.company_id == Company.id
    ).filter(
        Company.exchange == 'NYSE',
        Artifact.status == 'downloaded'
    ).count()

    nyse_pending = session.query(Artifact).join(
        Filing, Artifact.filing_id == Filing.id
    ).join(
        Company, Filing.company_id == Company.id
    ).filter(
        Company.exchange == 'NYSE',
        Artifact.status == 'pending_download'
    ).count()

    print('='*70)
    print('📊 DOWNLOAD PROGRESS - BOTH EXCHANGES')
    print('='*70)
    print()
    print('NASDAQ:')
    print(f'  Downloaded: {nasdaq_downloaded:,}')
    print(f'  Pending: {nasdaq_pending:,}')
    if nasdaq_downloaded + nasdaq_pending > 0:
        progress = nasdaq_downloaded / (nasdaq_downloaded + nasdaq_pending) * 100
        print(f'  Progress: {progress:.1f}%')
    print()
    print('NYSE:')
    print(f'  Downloaded: {nyse_downloaded:,}')
    print(f'  Pending: {nyse_pending:,}')
    if nyse_downloaded + nyse_pending > 0:
        progress = nyse_downloaded / (nyse_downloaded + nyse_pending) * 100
        print(f'  Progress: {progress:.1f}%')
    print()
"
```

### Check Running Processes

```bash
# Check if downloads are running
ps aux | grep -E "nasdaq_full_backfill|nyse_full_backfill" | grep -v grep
```

---

## 🔧 Process Management

### Check Process Status

```bash
# List running download processes
ps aux | grep python | grep backfill
```

### Stop Downloads (if needed)

**Stop NASDAQ:**
```bash
pkill -f nasdaq_full_backfill.py
```

**Stop NYSE:**
```bash
pkill -f nyse_full_backfill.py
```

**Stop both:**
```bash
pkill -f "full_backfill.py"
```

### Restart if Stopped

**Restart NASDAQ:**
```bash
source .venv/bin/activate
export DOWNLOAD_WORKERS=8
nohup python nasdaq_full_backfill.py --download-only >> logs/nasdaq_download.log 2>&1 &
```

**Restart NYSE:**
```bash
source .venv/bin/activate
export DOWNLOAD_WORKERS=8
nohup python nyse_full_backfill.py --download-only >> logs/nyse_download.log 2>&1 &
```

---

## 📈 Real-Time Monitoring Dashboard

### Create a Watch Script

**Save this as `watch_progress.sh`:**
```bash
#!/bin/bash

while true; do
    clear
    echo "========================================================================"
    echo "  Download Progress Monitor - $(date)"
    echo "========================================================================"
    echo ""

    # Check running processes
    echo "Running Processes:"
    ps aux | grep -E "nasdaq_full_backfill|nyse_full_backfill" | grep -v grep | \
    awk '{print "  PID: " $2 " - " $11 " " $12 " " $13}'
    echo ""

    # Check database progress
    source .venv/bin/activate && python -c "
from config.db import get_db_session
from models import Artifact, Filing, Company

with get_db_session() as session:
    # NASDAQ
    nasdaq_d = session.query(Artifact).join(Filing).join(Company).filter(
        Company.exchange == 'NASDAQ', Artifact.status == 'downloaded'
    ).count()
    nasdaq_p = session.query(Artifact).join(Filing).join(Company).filter(
        Company.exchange == 'NASDAQ', Artifact.status == 'pending_download'
    ).count()

    # NYSE
    nyse_d = session.query(Artifact).join(Filing).join(Company).filter(
        Company.exchange == 'NYSE', Artifact.status == 'downloaded'
    ).count()
    nyse_p = session.query(Artifact).join(Filing).join(Company).filter(
        Company.exchange == 'NYSE', Artifact.status == 'pending_download'
    ).count()

    print('NASDAQ:')
    nasdaq_total = nasdaq_d + nasdaq_p
    if nasdaq_total > 0:
        pct = nasdaq_d / nasdaq_total * 100
        print(f'  [{\"#\" * int(pct/2):<50}] {pct:.1f}%')
        print(f'  {nasdaq_d:,} / {nasdaq_total:,} artifacts')

    print()
    print('NYSE:')
    nyse_total = nyse_d + nyse_p
    if nyse_total > 0:
        pct = nyse_d / nyse_total * 100
        print(f'  [{\"#\" * int(pct/2):<50}] {pct:.1f}%')
        print(f'  {nyse_d:,} / {nyse_total:,} artifacts')
" 2>/dev/null

    echo ""
    echo "Press Ctrl+C to stop monitoring"
    sleep 5
done
```

**Make it executable and run:**
```bash
chmod +x watch_progress.sh
./watch_progress.sh
```

---

## ⚠️ Important Notes

### Resource Usage

**Both downloads running simultaneously:**
- **Workers:** 8 per exchange = 16 total concurrent workers
- **Database connections:** ~16 active connections
- **Network:** Both respect global 10 req/s rate limit (shared)
- **CPU:** Minimal (mostly I/O bound)
- **Memory:** ~500 MB total

**This is safe!** The rate limiter is global across all processes.

### Rate Limit Compliance

Both NASDAQ and NYSE downloads share the **same global rate limiter**:
- Maximum combined: 10 requests/second
- Each process respects the limit
- Total throughput: ~600-800 files/min (both combined)

### Expected Completion Times

| Exchange | Artifacts | Time (Sequential) | Time (Concurrent) |
|----------|-----------|-------------------|-------------------|
| NASDAQ | ~39,000 | ~11 hours | **2-3 hours** |
| NYSE | ~23,000 | ~6 hours | **1-2 hours** |
| **Total** | **~62,000** | **~17 hours** | **~3-5 hours** |

**Running both in parallel:** Still ~3-5 hours (they share rate limit)

---

## ✅ Quick Reference

### Start Both Downloads

```bash
# Terminal 1
cd /Users/hao/Desktop/FINAI/files/filings-etl
source .venv/bin/activate
export DOWNLOAD_WORKERS=8
nohup python nasdaq_full_backfill.py --download-only > logs/nasdaq_download.log 2>&1 &

# Terminal 2 (new window/tab)
cd /Users/hao/Desktop/FINAI/files/filings-etl
source .venv/bin/activate
export DOWNLOAD_WORKERS=8
nohup python nyse_full_backfill.py --download-only > logs/nyse_download.log 2>&1 &
```

### Monitor Progress

```bash
# Quick check
python -c "from config.db import get_db_session; from models import Artifact; s = get_db_session().__enter__(); print(f\"Downloaded: {s.query(Artifact).filter(Artifact.status=='downloaded').count()}\")"

# Detailed view
tail -f logs/nasdaq_download.log  # or nyse_download.log
```

### Check Status

```bash
# Are they running?
ps aux | grep backfill | grep -v grep

# How many done?
source .venv/bin/activate && python -c "from config.db import get_db_session; from models import Artifact; s = get_db_session().__enter__(); d = s.query(Artifact).filter(Artifact.status=='downloaded').count(); p = s.query(Artifact).filter(Artifact.status=='pending_download').count(); print(f'Done: {d}, Pending: {p}, Progress: {d/(d+p)*100:.1f}%')"
```

---

**Both downloads are now running! Check progress anytime with the commands above.** 🚀
