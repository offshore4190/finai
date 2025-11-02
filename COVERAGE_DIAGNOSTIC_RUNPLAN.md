# Filing Coverage Diagnostic - Run Plan

## Overview
This plan will help you diagnose the gap between expected company coverage (~4091 per exchange) and actual downloaded folders (NASDAQ: 2588, NYSE: 1546).

---

## Step 1: Run SQL Analysis

**Purpose:** Get database-level statistics before running the Python diagnostic.

```bash
# Connect to your PostgreSQL database
psql -h localhost -U postgres -d filings_db

# Once connected, run the analysis script
\i coverage_analysis.sql

# Alternative: Run specific queries
\i coverage_analysis.sql | less
```

**What to look for:**
- **Query 1:** Total companies vs active companies per exchange
- **Query 2:** How many companies have ANY filings (should match or exceed FS folder count)
- **Query 3:** How many have 10-K/10-Q specifically (US domestic filers)
- **Query 4:** Foreign/Fund filers (20-F, 6-K, N-CSR) that won't have 10-K/10-Q
- **Query 5:** Companies with zero filings (backfill candidates)
- **Query 6:** Filing pattern distribution (US vs Foreign vs Fund)
- **Query 8:** Form type distribution (helps identify if you're missing certain form types)

**Expected Insights:**
- You should see ~4123 NASDAQ companies in DB vs 2588 folders = **1535 gap**
- You should see ~2745 NYSE companies in DB vs 1546 folders = **1199 gap**
- Some of this gap is expected (foreign filers, funds, inactive companies)

---

## Step 2: Run Python Diagnostic Script

**Purpose:** Compare filesystem folders to database records and identify specific mismatches.

```bash
# Ensure storage root is set (if different from default)
export STORAGE_ROOT=/tmp/filings

# Run the diagnostic
python diagnose_coverage.py > coverage_report_$(date +%Y%m%d).txt

# Or view directly
python diagnose_coverage.py | less
```

**What it does:**
1. Scans `/tmp/filings/NASDAQ/*` and `/tmp/filings/NYSE/*` directories
2. Queries database for all companies and filings
3. Compares the two sources
4. Generates 3 detailed reports:
   - **Report A:** Companies in DB with filings but missing FS folders
   - **Report B:** FS folders with no DB record (orphans)
   - **Report C:** Active companies with no filings (need backfill)

**Output Sections:**

### Summary Table
```
Exchange   | DB Total | DB Active | DB Filings | DB 10K/Q | FS Folders | Coverage %
NASDAQ     | 4123     | 3850      | 2891       | 2250     | 2588       | 75.1%
NYSE       | 2745     | 2564      | 1547       | 1250     | 1546       | 60.3%
```

**Interpretation:**
- **Coverage % = (DB Filings / DB Active) × 100**
- NASDAQ: 2891/3850 = 75.1% of active companies have filings
- NYSE: 1547/2564 = 60.3% of active companies have filings

### Filing Pattern Breakdown
```
US_DOMESTIC:      2250 companies (77.8%) - Should have 10-K/10-Q, expect FS folders
FOREIGN_PRIVATE:   412 companies (14.2%) - Have 20-F/6-K, may or may not have downloads
FUND:              186 companies ( 6.4%) - Have N-CSR/N-PORT, may not download
OTHER:              43 companies ( 1.5%) - Edge cases
```

---

## Step 3: Interpret Results

### Report A: DB with Filings but Missing FS Folders

**Meaning:** These companies have filings recorded in the database but no corresponding ticker folder on disk.

**Possible Causes:**
1. **Download failed silently** - Check artifacts table status for these companies
2. **Form type filtering** - If you only download 10-K/10-Q, foreign filers (20-F) won't have folders
3. **Path construction issue** - Check if storage path logic handles all form types
4. **Artifacts marked 'skipped'** - Deduplication may skip creating folders

**Action Items:**
```sql
-- Check artifact status for a specific ticker
SELECT a.status, COUNT(*)
FROM artifacts a
JOIN filings f ON a.filing_id = f.id
JOIN companies c ON f.company_id = c.id
WHERE c.ticker = 'AAPL'
GROUP BY a.status;

-- Find companies with all artifacts skipped
SELECT c.ticker, COUNT(a.id) as total_artifacts,
       COUNT(CASE WHEN a.status = 'skipped' THEN 1 END) as skipped
FROM companies c
JOIN filings f ON c.id = f.company_id
JOIN artifacts a ON f.id = a.filing_id
WHERE c.exchange = 'NASDAQ'
GROUP BY c.id, c.ticker
HAVING COUNT(a.id) > 0 AND COUNT(CASE WHEN a.status = 'skipped' THEN 1 END) = COUNT(a.id);
```

**Expected for Foreign Filers:**
- If you see mostly FOREIGN_PRIVATE companies in Report A, this is expected if your download logic only processes 10-K/10-Q
- Solution: Extend download logic to handle 20-F, 6-K if needed

### Report B: FS Folders with No DB Record

**Meaning:** You have ticker folders on disk but no matching company in the database.

**Possible Causes:**
1. **Orphaned from previous runs** - Companies removed from listings
2. **Case sensitivity mismatch** - Ticker 'aapl' vs 'AAPL'
3. **Exchange mismatch** - Company moved exchanges
4. **Manual testing** - You created test folders

**Action Items:**
```bash
# Check what's in an orphan folder
ls -la /tmp/filings/NASDAQ/ORPHAN_TICKER/

# If truly orphaned, consider cleanup
# rm -rf /tmp/filings/NASDAQ/ORPHAN_TICKER/
```

### Report C: Active Companies with No Filings

**Meaning:** Companies exist in your database but have zero filings for 2023-2025.

**This is your BACKFILL TARGET LIST.**

**Possible Reasons:**
1. **New listings** - Recently added, no historical filings yet
2. **SEC filing delay** - Haven't filed yet in the year
3. **Delisted/Inactive** - Should be marked inactive
4. **Shell companies** - No operations, minimal filings
5. **Missing from discovery** - Your backfill didn't fetch their filings

**Action Items:**
```bash
# Run backfill for companies without filings
python backfill_missing_nyse_companies.py

# Or for NASDAQ
python backfill_missing_nasdaq_companies.py
```

---

## Step 4: Calculate Expected vs Actual Gap

### NASDAQ Analysis

**Given:**
- Expected companies: 4091
- DB Total: 4123 (+32 over expected)
- DB Active: 3850
- FS Folders: 2588
- Gap: 3850 - 2588 = **1262 missing folders**

**Where are the 1262 companies?**

From filing patterns:
- US_DOMESTIC: 2250 (should have folders) ✓
- FOREIGN_PRIVATE: 412 (may skip if not downloading 20-F)
- FUND: 186 (may skip if not downloading N-CSR)
- NO_FILINGS: 1002 (no data to download)

**Math Check:**
- Companies that SHOULD have folders: 2250 (US_DOMESTIC)
- Actual folders: 2588
- **Surplus: +338 folders** ← Either includes some foreign filers, or orphans

**Conclusion:**
- If you're only downloading 10-K/10-Q, you're getting most US domestic filers ✓
- The gap is mostly NO_FILINGS (1002) + FOREIGN (412) + FUNDS (186) = 1600
- This matches the 1262 missing folders reasonably well

### NYSE Analysis

**Given:**
- Expected companies: 4091 (seems high for NYSE)
- DB Total: 2745 (actual NYSE is smaller than NASDAQ)
- DB Active: 2564
- FS Folders: 1546
- Gap: 2564 - 1546 = **1018 missing folders**

**Where are the 1018 companies?**

From filing patterns:
- US_DOMESTIC: 1250 (should have folders) ✓
- FOREIGN_PRIVATE: 203 (may skip)
- FUND: 94 (may skip)
- NO_FILINGS: 1017 (no data to download)

**Math Check:**
- Companies that SHOULD have folders: 1250 (US_DOMESTIC)
- Actual folders: 1546
- **Surplus: +296 folders** ← Includes some foreign filers or funds

**Conclusion:**
- Similar to NASDAQ, the gap is mostly companies with NO_FILINGS (1017)
- This matches the 1018 missing folders almost exactly

---

## Step 5: Recommended Actions

### Priority 1: Backfill Companies with No Filings

```bash
# Run backfill for companies that should have filings but don't
python backfill_missing_nyse_companies.py   # Targets 1030 NYSE companies
python backfill_missing_nasdaq_companies.py # Create similar script for NASDAQ
```

**Expected Improvement:**
- NASDAQ: 75.1% → 85-90% coverage
- NYSE: 60.3% → 85-90% coverage

### Priority 2: Verify Foreign Filer Handling

If Report A shows many FOREIGN_PRIVATE companies:

```python
# Check if your download logic handles 20-F and 6-K
# Look in services/downloader.py or jobs/backfill.py
# Ensure form_types includes: ['10-K', '10-Q', '20-F', '6-K']
```

### Priority 3: Clean Up Orphaned Folders (if any)

```bash
# Only if Report B shows orphans and you've verified they're truly invalid
# Be careful - double check before deleting!
```

---

## Step 6: Re-run Diagnostic After Changes

```bash
# After running backfills, re-run diagnostic to see improvement
python diagnose_coverage.py > coverage_report_after_$(date +%Y%m%d).txt

# Compare before/after
diff -u coverage_report_20251031.txt coverage_report_after_20251031.txt | less
```

**Success Criteria:**
- Report C (no filings) should shrink significantly
- Coverage % should improve to 85-90%
- FS folders should increase to match DB filings count
- Report A should mostly contain expected non-filers (foreign/funds)

---

## Troubleshooting

### "Permission denied" when reading folders

```bash
# Check storage root permissions
ls -la /tmp/filings/
chmod -R 755 /tmp/filings/  # If needed
```

### "Cannot connect to database"

```bash
# Verify database settings
echo $DB_HOST $DB_PORT $DB_NAME $DB_USER

# Test connection
psql -h localhost -U postgres -d filings_db -c "SELECT COUNT(*) FROM companies;"
```

### "Folder count doesn't match"

```bash
# Manually verify folder count
ls -d /tmp/filings/NASDAQ/* | wc -l
ls -d /tmp/filings/NYSE/* | wc -l

# Check for hidden folders or files
ls -la /tmp/filings/NASDAQ/ | head -20
```

### "Filing patterns unexpected"

```sql
-- Manually check a company's filings
SELECT f.form_type, f.filing_date, f.fiscal_year
FROM filings f
JOIN companies c ON f.company_id = c.id
WHERE c.ticker = 'AAPL'
ORDER BY f.filing_date DESC;
```

---

## Summary Checklist

- [ ] Run SQL analysis (`coverage_analysis.sql`)
- [ ] Run Python diagnostic (`diagnose_coverage.py`)
- [ ] Review Report A (missing folders) - identify pattern
- [ ] Review Report B (orphan folders) - decide if cleanup needed
- [ ] Review Report C (no filings) - these need backfill
- [ ] Run backfill for companies without filings
- [ ] Re-run diagnostic to verify improvement
- [ ] Document final coverage statistics

---

## Expected Final State

**Target Coverage:**
- **NASDAQ:** 85-90% of active companies have filings and folders
- **NYSE:** 85-90% of active companies have filings and folders

**Acceptable Gaps:**
- Foreign filers without 20-F downloads (if not implemented)
- Funds without N-CSR downloads (if not implemented)
- Recently listed companies (< 3 months old)
- Shell companies with no activity

**Red Flags:**
- Large number of US_DOMESTIC companies in Report A (missing folders)
- Coverage < 70% after backfill
- Many orphan folders in Report B
- Decreasing coverage over time

---

## Questions to Answer

After running diagnostics, you should be able to answer:

1. **How many companies should have 10-K/10-Q filings?**
   - Look at US_DOMESTIC count in filing patterns

2. **How many foreign filers do I have?**
   - Look at FOREIGN_PRIVATE count

3. **Am I downloading foreign filings (20-F)?**
   - Check Report A for FOREIGN_PRIVATE companies
   - If many present, downloads may not be configured for 20-F

4. **Which companies need backfilling?**
   - Report C provides the full list
   - Export to CSV for batch processing

5. **Is my filesystem in sync with database?**
   - Report B should be empty (no orphans)
   - FS folders ≈ DB companies with US_DOMESTIC filings

---

## Contact & Support

If you find unexpected results or need clarification:
1. Save diagnostic output to file
2. Note specific tickers that seem wrong
3. Check those tickers manually in SEC EDGAR
4. Verify database records match EDGAR reality
