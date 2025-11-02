#!/bin/bash
#
# Monitor rate limit compliance during concurrent downloads
#
# This script monitors the download rate in real-time to ensure
# the system respects the SEC EDGAR 10 req/s rate limit.
#

echo "======================================================================="
echo "  SEC EDGAR Rate Limit Monitor"
echo "======================================================================="
echo ""
echo "Monitoring download rate to ensure <= 10 requests/second compliance"
echo "Press Ctrl+C to stop"
echo ""
echo "Time                 | Last 1s | Last 5s | Last 10s | Status"
echo "---------------------------------------------------------------------"

# Database connection parameters
DB_NAME="${DB_NAME:-filings_db}"
DB_USER="${DB_USER:-postgres}"
DB_HOST="${DB_HOST:-localhost}"

while true; do
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

    # Query to count downloads in different time windows
    QUERY="
    SELECT
        COUNT(*) FILTER (WHERE downloaded_at > NOW() - INTERVAL '1 second') as last_1s,
        COUNT(*) FILTER (WHERE downloaded_at > NOW() - INTERVAL '5 seconds') / 5.0 as last_5s,
        COUNT(*) FILTER (WHERE downloaded_at > NOW() - INTERVAL '10 seconds') / 10.0 as last_10s
    FROM artifacts
    WHERE status IN ('downloaded', 'skipped')
      AND downloaded_at IS NOT NULL;
    "

    # Execute query
    RESULT=$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -A -F'|' -c "$QUERY" 2>/dev/null)

    if [ $? -eq 0 ] && [ -n "$RESULT" ]; then
        # Parse results
        LAST_1S=$(echo "$RESULT" | cut -d'|' -f1)
        LAST_5S=$(echo "$RESULT" | cut -d'|' -f2)
        LAST_10S=$(echo "$RESULT" | cut -d'|' -f3)

        # Determine status
        if (( $(echo "$LAST_1S > 11" | bc -l) )); then
            STATUS="⚠️  VIOLATION"
        elif (( $(echo "$LAST_5S > 10.5" | bc -l) )); then
            STATUS="⚠️  WARNING"
        else
            STATUS="✅ OK"
        fi

        # Format output
        printf "%-20s | %7s | %7.1f | %8.1f | %s\n" \
            "$TIMESTAMP" "$LAST_1S" "$LAST_5S" "$LAST_10S" "$STATUS"
    else
        printf "%-20s | %s\n" "$TIMESTAMP" "Database not accessible"
    fi

    sleep 1
done
