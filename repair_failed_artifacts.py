#!/usr/bin/env python3
"""
Utility script to re-queue failed artifacts for another download attempt.
Supports filtering by exchange or processing all exchanges.
"""
import argparse
from typing import Tuple, Optional, List

import structlog

from config.db import get_db_session
from config.settings import settings
from models import Artifact, Filing, Company

logger = structlog.get_logger()


def _counts(session, exchanges: Optional[List[str]], max_retry: int) -> Tuple[int, int]:
    """Return total failed artifacts and how many exceeded retry limit."""
    query = session.query(Artifact).join(Filing).join(Company).filter(
        Artifact.status == 'failed'
    )

    if exchanges:
        query = query.filter(Company.exchange.in_(exchanges))

    total_failed = query.count()

    query_skipped = session.query(Artifact).join(Filing).join(Company).filter(
        Artifact.status == 'failed',
        Artifact.retry_count >= max_retry
    )

    if exchanges:
        query_skipped = query_skipped.filter(Company.exchange.in_(exchanges))

    skipped = query_skipped.count()

    return total_failed, skipped


def repair_failed_artifacts(
    exchanges: Optional[List[str]] = None,
    batch_size: int = 100,
    max_retry: Optional[int] = None
) -> Tuple[int, int, int]:
    """
    Re-queue failed artifacts whose retry_count is still below the max.

    Args:
        exchanges: List of exchange names to filter, or None for all exchanges
        batch_size: Number of artifacts to commit per batch
        max_retry: Max retry count (defaults to settings.artifact_retry_max)

    Returns:
        Tuple of (total_failed, requeued, skipped)
    """
    if max_retry is None:
        max_retry = settings.artifact_retry_max

    exchange_filter = exchanges if exchanges else ["ALL"]
    logger.info(
        "repair_started",
        exchanges=exchange_filter,
        batch_size=batch_size,
        max_retry=max_retry
    )

    with get_db_session() as session:
        total_failed, skipped = _counts(session, exchanges, max_retry)
        logger.info(
            "failed_artifacts_summary",
            exchanges=exchange_filter,
            total_failed=total_failed,
            eligible=total_failed - skipped,
            skipped=skipped
        )

        if total_failed == 0:
            logger.info("repair_no_failed_artifacts", exchanges=exchange_filter)
            return (0, 0, 0)

        # Build query for eligible artifact IDs
        query = session.query(Artifact.id).join(Filing).join(Company).filter(
            Artifact.status == 'failed',
            Artifact.retry_count < max_retry
        )

        if exchanges:
            query = query.filter(Company.exchange.in_(exchanges))

        eligible_ids = [artifact_id for (artifact_id,) in query.order_by(Artifact.id)]

        if not eligible_ids:
            logger.info("repair_no_eligible_artifacts", exchanges=exchange_filter)
            return (total_failed, 0, skipped)

        requeued = 0

        for i in range(0, len(eligible_ids), batch_size):
            batch_ids = eligible_ids[i:i + batch_size]

            updated = session.query(Artifact).filter(
                Artifact.id.in_(batch_ids)
            ).update(
                {Artifact.status: 'pending_download'},
                synchronize_session=False
            )

            session.commit()
            requeued += updated

            logger.info(
                "repair_batch_committed",
                batch_size=updated,
                requeued_total=requeued
            )

        logger.info(
            "repair_completed",
            exchanges=exchange_filter,
            total_failed=total_failed,
            requeued=requeued,
            skipped=skipped
        )

        return (total_failed, requeued, skipped)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair failed artifacts by re-queuing them for download."
    )
    parser.add_argument(
        "--exchange",
        type=str,
        default="ALL",
        help="Exchange to filter by (NASDAQ, NYSE, etc.) or ALL for all exchanges (default: ALL)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of artifacts to commit per batch (default: 100)"
    )
    parser.add_argument(
        "--max-retry",
        type=int,
        default=None,
        help=f"Maximum retry count (default: {settings.artifact_retry_max} from settings)"
    )

    args = parser.parse_args()

    # Parse exchange filter
    if args.exchange.upper() == "ALL":
        exchanges = None  # Process all exchanges
    else:
        exchanges = [args.exchange]

    total_failed, requeued, skipped = repair_failed_artifacts(
        exchanges=exchanges,
        batch_size=args.batch_size,
        max_retry=args.max_retry
    )

    logger.info(
        "repair_summary",
        exchange=args.exchange,
        total_failed=total_failed,
        requeued=requeued,
        skipped=skipped,
        batch_size=args.batch_size
    )


if __name__ == "__main__":
    main()
