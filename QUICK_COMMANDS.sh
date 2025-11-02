#!/bin/bash
# =============================================================================
# Filing Coverage Diagnostic - Quick Commands
# =============================================================================

# Set storage root (adjust if needed)
export STORAGE_ROOT=/tmp/filings

# =============================================================================
# OPTION 1: Run Full Diagnostic (Python Script)
# =============================================================================

echo "Running full diagnostic..."
python diagnose_coverage.py | tee coverage_report_$(date +%Y%m%d_%H%M%S).txt

# =============================================================================
# OPTION 2: Run SQL Analysis Only
# =============================================================================

# Run all SQL queries
# psql -h localhost -U postgres -d filings_db -f coverage_analysis.sql

# =============================================================================
# OPTION 3: Quick Manual Checks
# =============================================================================

# Count filesystem folders
echo "=== Filesystem Folder Counts ==="
echo "NASDAQ: $(find /tmp/filings/NASDAQ -maxdepth 1 -type d | tail -n +2 | wc -l)"
echo "NYSE: $(find /tmp/filings/NYSE -maxdepth 1 -type d | tail -n +2 | wc -l)"
echo "NYSE American: $(find /tmp/filings/NYSE\ American -maxdepth 1 -type d 2>/dev/null | tail -n +2 | wc -l)"
echo "NYSE Arca: $(find /tmp/filings/NYSE\ Arca -maxdepth 1 -type d 2>/dev/null | tail -n +2 | wc -l)"

# =============================================================================
# OPTION 4: Individual SQL Queries
# =============================================================================

# Company counts
echo "=== Database Company Counts ==="
psql -h localhost -U postgres -d filings_db -c "
SELECT exchange, COUNT(*) as total, COUNT(CASE WHEN is_active THEN 1 END) as active
FROM companies
WHERE exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
GROUP BY exchange ORDER BY total DESC;
"

# Companies with filings
echo "=== Companies with Filings (2023-2025) ==="
psql -h localhost -U postgres -d filings_db -c "
SELECT c.exchange, COUNT(DISTINCT c.id) as companies_with_filings
FROM companies c
JOIN filings f ON c.id = f.company_id
WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
  AND f.fiscal_year BETWEEN 2023 AND 2025
GROUP BY c.exchange ORDER BY companies_with_filings DESC;
"

# Companies without filings
echo "=== Active Companies WITHOUT Filings ==="
psql -h localhost -U postgres -d filings_db -c "
SELECT exchange, COUNT(*) as no_filings_count
FROM companies c
WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
  AND c.is_active = true
  AND NOT EXISTS (SELECT 1 FROM filings f WHERE f.company_id = c.id)
GROUP BY exchange ORDER BY no_filings_count DESC;
"

# =============================================================================
# OPTION 5: Export Gap Lists for Analysis
# =============================================================================

# Export companies without filings (NYSE)
echo "=== Exporting NYSE companies without filings ==="
psql -h localhost -U postgres -d filings_db -t -A -F"," -o nyse_no_filings.csv -c "
SELECT ticker, cik, company_name, exchange, created_at
FROM companies c
WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
  AND c.is_active = true
  AND NOT EXISTS (SELECT 1 FROM filings f WHERE f.company_id = c.id)
ORDER BY ticker;
"

# Export companies without filings (NASDAQ)
echo "=== Exporting NASDAQ companies without filings ==="
psql -h localhost -U postgres -d filings_db -t -A -F"," -o nasdaq_no_filings.csv -c "
SELECT ticker, cik, company_name, exchange, created_at
FROM companies c
WHERE c.exchange = 'NASDAQ'
  AND c.is_active = true
  AND NOT EXISTS (SELECT 1 FROM filings f WHERE f.company_id = c.id)
ORDER BY ticker;
"

# =============================================================================
# OPTION 6: Sample Data Inspection
# =============================================================================

# Show sample of companies with different filing patterns
echo "=== Sample Companies by Filing Pattern ==="
psql -h localhost -U postgres -d filings_db -c "
WITH patterns AS (
  SELECT c.ticker, c.exchange,
    array_agg(DISTINCT f.form_type ORDER BY f.form_type) as forms,
    CASE
      WHEN bool_or(f.form_type IN ('10-K','10-Q')) THEN 'US_DOMESTIC'
      WHEN bool_or(f.form_type IN ('20-F','6-K')) THEN 'FOREIGN'
      WHEN bool_or(f.form_type LIKE 'N-%') THEN 'FUND'
      ELSE 'OTHER'
    END as pattern
  FROM companies c
  LEFT JOIN filings f ON c.id = f.company_id AND f.fiscal_year >= 2023
  WHERE c.exchange IN ('NASDAQ','NYSE')
  GROUP BY c.ticker, c.exchange
)
SELECT pattern, COUNT(*) as count, array_agg(ticker ORDER BY ticker LIMIT 5) as examples
FROM patterns
GROUP BY pattern ORDER BY count DESC;
"

# =============================================================================
# OPTION 7: Verify Specific Ticker
# =============================================================================

verify_ticker() {
    TICKER=$1
    echo "=== Checking ticker: $TICKER ==="

    # Check database
    psql -h localhost -U postgres -d filings_db -c "
    SELECT c.ticker, c.exchange, c.is_active,
           COUNT(f.id) as filings,
           array_agg(DISTINCT f.form_type ORDER BY f.form_type) as forms
    FROM companies c
    LEFT JOIN filings f ON c.id = f.company_id AND f.fiscal_year >= 2023
    WHERE c.ticker = '$TICKER'
    GROUP BY c.ticker, c.exchange, c.is_active;
    "

    # Check filesystem
    echo ""
    echo "Filesystem folders:"
    for exchange in "NASDAQ" "NYSE" "NYSE American" "NYSE Arca"; do
        if [ -d "/tmp/filings/$exchange/$TICKER" ]; then
            count=$(find "/tmp/filings/$exchange/$TICKER" -type d | wc -l)
            echo "  $exchange/$TICKER: exists ($count subdirs)"
        fi
    done
}

# Uncomment to verify a specific ticker
# verify_ticker "AAPL"

# =============================================================================
# OPTION 8: Generate Summary Statistics
# =============================================================================

generate_summary() {
    echo "=== Filing Coverage Summary ==="
    echo "Generated: $(date)"
    echo ""

    # Filesystem
    echo "FILESYSTEM FOLDERS:"
    echo "  NASDAQ:       $(find /tmp/filings/NASDAQ -maxdepth 1 -type d 2>/dev/null | tail -n +2 | wc -l)"
    echo "  NYSE:         $(find /tmp/filings/NYSE -maxdepth 1 -type d 2>/dev/null | tail -n +2 | wc -l)"
    echo "  NYSE American: $(find /tmp/filings/NYSE\ American -maxdepth 1 -type d 2>/dev/null | tail -n +2 | wc -l)"
    echo "  NYSE Arca:    $(find /tmp/filings/NYSE\ Arca -maxdepth 1 -type d 2>/dev/null | tail -n +2 | wc -l)"
    echo ""

    # Database
    echo "DATABASE COMPANIES:"
    psql -h localhost -U postgres -d filings_db -t -c "
    SELECT
      '  ' || exchange || ': ' ||
      COUNT(*) || ' total, ' ||
      COUNT(CASE WHEN is_active THEN 1 END) || ' active, ' ||
      (SELECT COUNT(DISTINCT company_id) FROM filings f WHERE f.company_id = ANY(array_agg(c.id))) || ' with filings'
    FROM companies c
    WHERE exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
    GROUP BY exchange ORDER BY exchange;
    "
}

# Uncomment to generate summary
# generate_summary

echo ""
echo "=== Commands Available ==="
echo "To run full diagnostic:"
echo "  python diagnose_coverage.py"
echo ""
echo "To run SQL analysis:"
echo "  psql -h localhost -U postgres -d filings_db -f coverage_analysis.sql"
echo ""
echo "To generate summary:"
echo "  bash QUICK_COMMANDS.sh (or source and call generate_summary)"
echo ""
echo "To verify specific ticker:"
echo "  source QUICK_COMMANDS.sh && verify_ticker AAPL"
