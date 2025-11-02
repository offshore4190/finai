#!/bin/bash
# NASDAQ Download Progress Monitor
# Run this script anytime to check progress

echo "================================================================================"
echo "              NASDAQ FILINGS DOWNLOAD - PROGRESS MONITOR"
echo "================================================================================"
echo ""

# Check if discovery process is running
if pgrep -f "nasdaq_full_backfill.py" > /dev/null; then
    echo "✅ Discovery process: RUNNING"
else
    echo "❌ Discovery process: NOT RUNNING"
fi

echo ""
echo "--------------------------------------------------------------------------------"
echo "FILING DISCOVERY PROGRESS"
echo "--------------------------------------------------------------------------------"

# Database statistics
docker exec filings_postgres psql -U postgres -d filings_db -c "
SELECT
    COUNT(DISTINCT c.id) as nasdaq_companies_total,
    COUNT(DISTINCT CASE WHEN f.id IS NOT NULL THEN c.id END) as companies_with_filings,
    COUNT(f.id) as total_filings_discovered,
    COUNT(DISTINCT CASE WHEN a.status = 'pending_download' THEN a.id END) as pending_artifacts,
    COUNT(DISTINCT CASE WHEN a.status = 'downloaded' THEN a.id END) as downloaded_artifacts
FROM companies c
LEFT JOIN filings f ON f.company_id = c.id AND f.fiscal_year >= 2023
LEFT JOIN artifacts a ON a.filing_id = f.id
WHERE c.exchange = 'NASDAQ';
" -t

echo ""
echo "--------------------------------------------------------------------------------"
echo "TOP 10 COMPANIES BY FILING COUNT"
echo "--------------------------------------------------------------------------------"

docker exec filings_postgres psql -U postgres -d filings_db -c "
SELECT
    c.ticker,
    c.company_name,
    COUNT(f.id) as filings
FROM companies c
JOIN filings f ON f.company_id = c.id
WHERE c.exchange = 'NASDAQ' AND f.fiscal_year >= 2023
GROUP BY c.ticker, c.company_name
ORDER BY filings DESC
LIMIT 10;
" -t

echo ""
echo "--------------------------------------------------------------------------------"
echo "DOWNLOAD STATISTICS"
echo "--------------------------------------------------------------------------------"

docker exec filings_postgres psql -U postgres -d filings_db -c "
SELECT
    status,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 1) as percentage
FROM artifacts a
JOIN filings f ON a.filing_id = f.id
JOIN companies c ON f.company_id = c.id
WHERE c.exchange = 'NASDAQ'
GROUP BY status
ORDER BY count DESC;
" -t

echo ""
echo "--------------------------------------------------------------------------------"
echo "STORAGE USAGE"
echo "--------------------------------------------------------------------------------"

if [ -d "/tmp/filings/NASDAQ" ]; then
    echo "NASDAQ filings directory size:"
    du -sh /tmp/filings/NASDAQ 2>/dev/null || echo "  Not yet created"
    echo ""
    echo "Total file count:"
    find /tmp/filings/NASDAQ -type f 2>/dev/null | wc -l | xargs echo "  Files:"
else
    echo "  NASDAQ directory not yet created"
fi

echo ""
echo "--------------------------------------------------------------------------------"
echo "ESTIMATED PROGRESS"
echo "--------------------------------------------------------------------------------"

# Calculate progress percentage
docker exec filings_postgres psql -U postgres -d filings_db -c "
SELECT
    ROUND(COUNT(DISTINCT CASE WHEN f.id IS NOT NULL THEN c.id END) * 100.0 / COUNT(DISTINCT c.id), 1) as discovery_progress_pct,
    4091 - COUNT(DISTINCT CASE WHEN f.id IS NOT NULL THEN c.id END) as companies_remaining
FROM companies c
LEFT JOIN filings f ON f.company_id = c.id AND f.fiscal_year >= 2023
WHERE c.exchange = 'NASDAQ';
" -t

echo ""
echo "================================================================================"
echo "                            USEFUL COMMANDS"
echo "================================================================================"
echo ""
echo "Check discovery process logs:"
echo "  tail -f (look for process output in terminal)"
echo ""
echo "Check database filings count:"
echo "  docker exec filings_postgres psql -U postgres -d filings_db -c \"SELECT COUNT(*) FROM filings WHERE fiscal_year >= 2023;\""
echo ""
echo "Check specific company:"
echo "  docker exec filings_postgres psql -U postgres -d filings_db -c \"SELECT * FROM filings WHERE company_id = (SELECT id FROM companies WHERE ticker = 'AAPL');\""
echo ""
echo "List downloaded files for a company:"
echo "  ls -lh /tmp/filings/NASDAQ/AAPL/"
echo ""
echo "================================================================================"
