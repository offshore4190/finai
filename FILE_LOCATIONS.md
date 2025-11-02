# 📂 Downloaded Files Location Guide

## 🎯 Quick Answer

**All downloaded SEC filings are stored at:**
```
/tmp/filings/
```

**Total Storage Used:** ~110 GB
**Total Files:** 91,223 files (42,707 HTML + 48,516 images)
**Total Companies:** 4,192 companies with downloaded files

---

## 📁 Directory Structure

```
/tmp/filings/
├── NASDAQ/           (2,595 companies, 62 GB)
│   ├── AAPL/
│   ├── MSFT/
│   ├── GOOGL/
│   └── ...
├── NYSE/             (1,553 companies, 48 GB)
│   ├── JPM/
│   ├── BAC/
│   ├── WMT/
│   └── ...
├── NYSE American/    (42 companies, 4.3 MB)
└── NYSE Arca/        (14 companies, 40 KB)
```

---

## 📄 File Naming Convention

### Format
```
{TICKER}_{YEAR}_{PERIOD}_{DATE}.{extension}
```

### Examples
```
AAPL_2024_FY_01-11-2024.html        # Apple 10-K annual report
MSFT_2024_Q1_30-01-2024.html        # Microsoft Q1 10-Q
JPM_2023_Q3_13-10-2023.html         # JPMorgan Q3 10-Q
TSLA_2024_FY_27-01-2024_image-001.jpg  # Tesla annual report image
```

### Period Codes
- `FY` = Fiscal Year (10-K annual report)
- `Q1` = Quarter 1 (10-Q)
- `Q2` = Quarter 2 (10-Q)
- `Q3` = Quarter 3 (10-Q)
- `Q4` = Quarter 4 (10-Q)

---

## 🗂️ Full Path Examples

### Apple (AAPL)
```bash
/tmp/filings/NASDAQ/AAPL/
├── 2023/
│   ├── AAPL_2023_FY_03-11-2023.html
│   ├── AAPL_2023_FY_03-11-2023_image-002.jpg
│   ├── AAPL_2023_Q1_03-02-2023.html
│   └── ...
├── 2024/
│   ├── AAPL_2024_FY_01-11-2024.html
│   ├── AAPL_2024_Q1_02-02-2024.html
│   └── ...
└── 2025/
    ├── AAPL_2025_Q1_01-08-2025.html
    └── ...
```

### Microsoft (MSFT)
```bash
/tmp/filings/NASDAQ/MSFT/2024/
├── MSFT_2024_FY_30-07-2024.html      (6.5 MB - Annual Report)
├── MSFT_2024_Q1_25-04-2024.html      (5.4 MB)
├── MSFT_2024_Q1_30-01-2024.html      (5.4 MB)
└── MSFT_2024_Q1_30-10-2024.html      (4.1 MB)
```

### JPMorgan (JPM)
```bash
/tmp/filings/NYSE/JPM/2024/
├── JPM_2024_FY_28-02-2024.html
├── JPM_2024_Q1_12-04-2024.html
├── JPM_2024_Q2_12-07-2024.html
└── JPM_2024_Q3_11-10-2024.html
```

---

## 💾 Storage Breakdown

| Exchange | Companies | Storage | Files |
|----------|-----------|---------|-------|
| **NASDAQ** | 2,595 | 62 GB | ~45,000 |
| **NYSE** | 1,553 | 48 GB | ~38,000 |
| **NYSE American** | 42 | 4.3 MB | ~120 |
| **NYSE Arca** | 14 | 40 KB | ~40 |
| **Total** | 4,192 | **110 GB** | **91,223** |

---

## 🔍 How to Find Files

### Browse by Company Ticker
```bash
# List all Apple filings
ls -R /tmp/filings/NASDAQ/AAPL/

# List Microsoft 2024 filings
ls /tmp/filings/NASDAQ/MSFT/2024/

# Find JPMorgan annual reports (10-K)
find /tmp/filings/NYSE/JPM -name "*_FY_*.html"
```

### Search for Specific Filing Type
```bash
# Find all 10-K annual reports
find /tmp/filings -name "*_FY_*.html"

# Find all Q1 reports
find /tmp/filings -name "*_Q1_*.html"

# Find all 2024 filings
find /tmp/filings -path "*/2024/*" -name "*.html"
```

### Count Files by Company
```bash
# Count AAPL files
find /tmp/filings/NASDAQ/AAPL -type f | wc -l

# Count all NASDAQ files
find /tmp/filings/NASDAQ -type f | wc -l
```

### Find Recent Downloads
```bash
# Files downloaded in last hour
find /tmp/filings -type f -mmin -60

# Files downloaded today
find /tmp/filings -type f -mtime 0
```

---

## 📊 File Statistics

### By Type
```
HTML Files:   42,707 files
Image Files:  48,516 files (jpg, png, gif)
Total Files:  91,223 files
```

### By Exchange
```
NASDAQ:        ~49% of total (62 GB)
NYSE:          ~44% of total (48 GB)
NYSE American:  ~4% of total (4.3 MB)
NYSE Arca:     <1% of total (40 KB)
```

---

## 🛠️ Accessing Files

### Command Line
```bash
# Open file in browser
open /tmp/filings/NASDAQ/AAPL/2024/AAPL_2024_FY_01-11-2024.html

# View file with less
less /tmp/filings/NASDAQ/MSFT/2024/MSFT_2024_Q1_30-01-2024.html

# Copy files to another location
cp -r /tmp/filings/NASDAQ/AAPL ~/Desktop/AAPL_filings/
```

### Finder (macOS)
```bash
# Open in Finder
open /tmp/filings/

# Navigate to specific company
open /tmp/filings/NASDAQ/AAPL/
```

### Python
```python
from pathlib import Path

# List all AAPL filings
aapl_path = Path("/tmp/filings/NASDAQ/AAPL")
for filing in aapl_path.rglob("*.html"):
    print(filing)

# Read a filing
filing_path = "/tmp/filings/NASDAQ/AAPL/2024/AAPL_2024_FY_01-11-2024.html"
with open(filing_path, 'r') as f:
    content = f.read()
```

---

## 📝 Configuration

### Storage Root Setting
The storage location is configured in:

**Environment Variable:**
```bash
export STORAGE_ROOT=/tmp/filings
```

**Configuration File:** `.env`
```
STORAGE_ROOT=/tmp/filings
```

### Change Storage Location
To change where files are stored:

1. Update `.env` file:
```bash
STORAGE_ROOT=/path/to/your/storage
```

2. Or set environment variable:
```bash
export STORAGE_ROOT=/path/to/your/storage
```

3. Re-run downloads (existing files won't move automatically)

---

## ⚠️ Important Notes

### Temporary Storage Warning
**⚠️ `/tmp/` files may be deleted on system reboot!**

If you want permanent storage, consider moving to:
```bash
# Option 1: User directory
STORAGE_ROOT=~/Documents/SEC_Filings

# Option 2: External drive
STORAGE_ROOT=/Volumes/External/SEC_Filings

# Option 3: Network storage
STORAGE_ROOT=/mnt/network/SEC_Filings
```

### Moving Existing Files
```bash
# Create new location
mkdir -p ~/Documents/SEC_Filings

# Move files
mv /tmp/filings/* ~/Documents/SEC_Filings/

# Update .env
echo "STORAGE_ROOT=$HOME/Documents/SEC_Filings" >> .env
```

---

## 🔗 Related Paths

### Database
```
Host: localhost
Port: 5432
Database: filings_db
```

### Configuration Files
```
/Users/hao/Desktop/FINAI/files/filings-etl/.env
/Users/hao/Desktop/FINAI/files/filings-etl/config/settings.py
```

### Scripts
```
/Users/hao/Desktop/FINAI/files/filings-etl/backfill_concurrent.py
/Users/hao/Desktop/FINAI/files/filings-etl/diagnose_coverage.py
```

---

## 📈 Growth Estimates

### Current State (After Initial Backfill)
- Companies: 4,192
- Storage: 110 GB
- Files: 91,223

### After Full Backfill (In Progress)
- Companies: ~5,500-6,000 (expected)
- Storage: ~130-150 GB (expected)
- Files: ~110,000-120,000 (expected)

### Annual Growth (With Incremental Updates)
- New filings per year: ~16,000
- Storage growth: ~20-30 GB/year
- Image files: ~20,000/year

---

## 🚀 Quick Access Commands

```bash
# Go to storage root
cd /tmp/filings

# List all exchanges
ls /tmp/filings/

# Find a specific company
find /tmp/filings -type d -name "AAPL"

# Count total companies
ls -d /tmp/filings/*/* | wc -l

# Check storage usage
du -sh /tmp/filings/*

# View most recent downloads
find /tmp/filings -type f -mtime 0
```

---

**Last Updated:** 2025-10-31
**Storage Location:** `/tmp/filings/`
**Total Storage:** 110 GB
**Total Companies:** 4,192
