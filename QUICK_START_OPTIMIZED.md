# Quick Start Guide - Optimized Concurrent Downloads

## 🚀 Quick Start (5 minutes)

### 1. Activate Environment
```bash
python3 -m venv venv 
source .venv/bin/activate  # （zsh）or venv/bin/activate
```

### 2. Run Optimized Downloads

**Test with small dataset first:**
```bash
# NASDAQ - 10 companies
python nasdaq_full_backfill.py --download-only --limit 10

# NYSE - 10 companies
python nyse_full_backfill.py --download-only --limit 10
```

**Full backfill (production):**
```bash
# NASDAQ - all ~4,091 companies
python nasdaq_full_backfill.py --download-only

# NYSE - all ~2,353 companies
python nyse_full_backfill.py --download-only
```

### 3. Monitor (Optional)

In a separate terminal:
```bash
./monitor_rate_limit.sh
```

---

## ⚙️ Configuration

### Default Settings
- `DOWNLOAD_WORKERS=8` (optimized, 4.4x faster)
- Rate limit: 10 req/s (SEC requirement)
- Auto-retry: 3 attempts per artifact

### Adjust Workers

**Via environment variable:**
```bash
export DOWNLOAD_WORKERS=4  # More conservative
export DOWNLOAD_WORKERS=8  # Default (recommended)
```

**Via .env file:**
```bash
echo "DOWNLOAD_WORKERS=8" >> .env
```

### Rollback to Sequential
```bash
export DOWNLOAD_WORKERS=1  # Disables concurrency
```

---

## 📊 Expected Performance

| Scenario | Sequential | Optimized (8 workers) | Speedup |
|----------|-----------|----------------------|---------|
| Small files | ~100 files/min | ~500 files/min | 5x |
| Large files | ~35 files/min | ~150 files/min | 4.3x |
| Average | ~116 files/min | ~512 files/min | **4.4x** |

### Time Estimates (Full Backfill)

**NASDAQ (~4,091 companies, ~40,000 artifacts):**
- Sequential: ~7 hours
- Optimized: **~1.5 hours** ⏱️

**NYSE (~2,353 companies, ~23,000 artifacts):**
- Sequential: ~4 hours
- Optimized: **~1 hour** ⏱️

---

## ✅ Safety Checklist

Before running full backfill:

- [ ] Database is accessible (`psql -U postgres -d filings_db -c "SELECT 1;"`)
- [ ] Storage has enough space (`df -h /data/filings`)
- [ ] User-Agent is configured (`.env` file has `SEC_USER_AGENT`)
- [ ] Test run completed successfully (`--limit 10`)
- [ ] Rate limit monitoring available (optional)

---

## 🔍 Monitoring

### Check Progress

```bash
# Count downloaded artifacts
psql -U postgres -d filings_db -c "
SELECT status, COUNT(*)
FROM artifacts
GROUP BY status;
"
```

### Check Download Rate

```bash
# In another terminal
./monitor_rate_limit.sh

# Expected output:
# Time                 | Last 1s | Last 5s | Last 10s | Status
# --------------------------------------------------------------
# 2025-10-30 08:00:00  |      10 |     9.8 |      9.5 | ✅ OK
```

### Check Logs

```bash
# Follow logs (if using file logging)
tail -f logs/filings-etl.log | grep "download_progress"
```

---

## 🐛 Troubleshooting

### Issue: Downloads seem slow

**Check:**
```bash
# Verify workers setting
python -c "from config.settings import settings; print(f'Workers: {settings.download_workers}')"

# Should output: Workers: 8
```

### Issue: Rate limit errors (429)

**Check compliance:**
```bash
./monitor_rate_limit.sh
```

If violations detected:
```bash
# Reduce workers
export DOWNLOAD_WORKERS=4
```

### Issue: Database connection errors

**Check:**
```bash
psql -U postgres -d filings_db -c "SELECT COUNT(*) FROM companies;"
```

If fails, check `docker-compose ps` or restart PostgreSQL.

### Issue: Want to rollback

```bash
# Disable concurrency immediately
export DOWNLOAD_WORKERS=1

# Run with sequential processing
python nasdaq_full_backfill.py --download-only
```

---

## 📈 Performance Verification

### Quick Benchmark

```bash
# Run benchmark script
python benchmark_concurrent_download.py

# Expected output:
# Sequential: ~116 files/min
# Concurrent: ~512 files/min
# Speedup: 4.4x
```

### Measure Real Performance

```bash
# Baseline (sequential)
time (export DOWNLOAD_WORKERS=1 && python nasdaq_full_backfill.py --download-only --limit 100)

# Optimized (concurrent)
time (export DOWNLOAD_WORKERS=8 && python nasdaq_full_backfill.py --download-only --limit 100)

# Compare times
```

---

## 🎯 Recommended Workflow

### First Time Setup

```bash
# 1. Test with 10 companies
export DOWNLOAD_WORKERS=8
python nasdaq_full_backfill.py --download-only --limit 10

# 2. Verify downloads
psql -U postgres -d filings_db -c "SELECT COUNT(*) FROM artifacts WHERE status='downloaded';"

# 3. Test with 100 companies
python nasdaq_full_backfill.py --download-only --limit 100

# 4. Monitor rate limit
./monitor_rate_limit.sh
```

### Production Run

```bash
# Run in background with logging
nohup python nasdaq_full_backfill.py --download-only > logs/nasdaq_backfill.log 2>&1 &

# Monitor progress
tail -f logs/nasdaq_backfill.log

# Check rate limit (optional, another terminal)
./monitor_rate_limit.sh
```

---

## 📞 Need Help?

**Check these files:**
1. `OPTIMIZATION_SUMMARY.md` - Complete technical documentation
2. `USER_GUIDE.md` - Comprehensive user guide
3. `TROUBLESHOOTING_CN.md` - Common issues and solutions

**Verify setup:**
```bash
# Test imports
python -c "
from config.settings import settings
from utils.rate_limiter import SECRateLimiter
print('✅ All imports successful')
print(f'Download workers: {settings.download_workers}')
"
```

---

**Happy downloading! 🚀**

With 8 workers, you'll complete your backfills **4.4x faster** while maintaining SEC compliance and data integrity.
