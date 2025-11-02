#!/bin/bash
# Complete all pending artifact downloads
# Loops until pending_download count reaches 0

set -e

cd "$(dirname "$0")"
source venv/bin/activate

ROUND=1

echo "================================================================================"
echo "  STARTING DOWNLOAD LOOP - $(date)"
echo "================================================================================"

while true; do
    echo ""
    echo "=== ROUND $ROUND: Downloading pending artifacts ($(date)) ==="

    # Run download script
    python download_all_pending.py --workers 8

    # Check remaining pending artifacts
    PENDING=$(python -c "
from config.db import get_db_session
from models import Artifact
with get_db_session() as session:
    count = session.query(Artifact).filter(Artifact.status == 'pending_download').count()
    print(count)
")

    echo ""
    echo "Pending artifacts remaining: $PENDING"

    if [ "$PENDING" -eq "0" ]; then
        echo ""
        echo "================================================================================"
        echo "  ALL ARTIFACTS DOWNLOADED! - $(date)"
        echo "================================================================================"
        break
    fi

    echo "Sleeping 30 seconds before next round..."
    sleep 30

    ROUND=$((ROUND + 1))
done

# Run final audit
echo ""
echo "Running final audit..."
python audit_state.py

echo ""
echo "================================================================================"
echo "  DOWNLOAD LOOP COMPLETED - $(date)"
echo "================================================================================"
