#!/bin/bash
# Real-time NASDAQ Backfill Monitor
# Updates every 10 seconds

echo "========================================="
echo "  NASDAQ BACKFILL - LIVE MONITOR"
echo "========================================="
echo ""
echo "Press Ctrl+C to stop monitoring"
echo ""

while true; do
    clear
    echo "========================================="
    echo "  NASDAQ BACKFILL - LIVE MONITOR"
    echo "========================================="
    echo ""
    date
    echo ""

    # Check if process is running
    if pgrep -f "nasdaq_full_backfill.py" > /dev/null; then
        echo "✅ Status: RUNNING (PID: $(pgrep -f nasdaq_full_backfill.py))"
    else
        echo "❌ Status: NOT RUNNING"
        break
    fi

    echo ""
    echo "-----------------------------------------"
    echo "LATEST ACTIVITY (Last 15 companies):"
    echo "-----------------------------------------"
    tail -500 nasdaq_full_backfill.log | grep "processing_company" | tail -15 | \
        sed 's/.*progress=\([0-9]*\/[0-9]*\).*ticker=\([A-Z]*\).*/  [\1] \2/'

    echo ""
    echo "-----------------------------------------"
    echo "PROGRESS CHECKPOINTS:"
    echo "-----------------------------------------"
    tail -1000 nasdaq_full_backfill.log | grep "progress_checkpoint" | tail -5

    echo ""
    echo "-----------------------------------------"
    echo "DATABASE STATUS:"
    echo "-----------------------------------------"
    docker exec filings_postgres psql -U postgres -d filings_db -t -c "
    SELECT
        COUNT(DISTINCT c.id) as companies_discovered,
        COUNT(f.id) as filings_found,
        COUNT(CASE WHEN a.status = 'pending_download' THEN 1 END) as pending,
        COUNT(CASE WHEN a.status = 'downloaded' THEN 1 END) as downloaded
    FROM companies c
    LEFT JOIN filings f ON f.company_id = c.id AND f.fiscal_year >= 2023
    LEFT JOIN artifacts a ON a.filing_id = f.id
    WHERE c.exchange = 'NASDAQ';" 2>/dev/null | head -1

    echo ""
    echo "-----------------------------------------"
    echo "Commands:"
    echo "  Ctrl+C          - Stop monitoring"
    echo "  tail -f nasdaq_full_backfill.log - View full logs"
    echo "  ./monitor_progress.sh - Full statistics"
    echo "-----------------------------------------"

    sleep 10
done

echo ""
echo "Monitoring stopped."
