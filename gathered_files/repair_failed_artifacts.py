#!/usr/bin/env python3
"""
Utility script to re-queue failed NYSE artifacts for another download attempt.
"""
import argparse
from typing import Tuple

import structlog

from config.db import get_db_session
from config.settings import settings
from models import Artifact, Filing, Company

logger = structlog.get_logger()


def _counts(session, max_retry: int) -> Tuple[int, int]:
    """Return total NYSE failed artifacts and how many exceeded retry limit."""
    total_failed = session.query(Artifact).join(Filing).join(Company).filter(
        Company.exchange == 'NYSE',
        Artifact.status == 'failed'
    ).count()

    skipped = session.query(Artifact).join(Filing).join(Company).filter(
        Company.exchange == 'NYSE',
        Artifact.status == 'failed',
        Artifact.retry_count >= max_retry
    ).count()

    return total_failed, skipped


def repair_failed_artifacts(batch_size: int = 100) -> Tuple[int, int, int]:
    """
    Re-queue failed NYSE artifacts whose retry_count is still below the max.

    Returns:
        Tuple of (total_failed, requeued, skipped)
    """
    max_retry = settings.artifact_retry_max
    logger.info(
        "nyse_repair_started",
        batch_size=batch_size,
        max_retry=max_retry
    )

    with get_db_session() as session:
        total_failed, skipped = _counts(session, max_retry)
        logger.info(
            "nyse_failed_artifacts_summary",
            total_failed=total_failed,
            eligible=total_failed - skipped,
            skipped=skipped
        )

        if total_failed == 0:
            logger.info("nyse_repair_no_failed_artifacts")
            return (0, 0, 0)

        eligible_ids = [
            artifact_id
            for (artifact_id,) in session.query(Artifact.id).join(Filing).join(Company).filter(
                Company.exchange == 'NYSE',
                Artifact.status == 'failed',
                Artifact.retry_count < max_retry
            ).order_by(Artifact.id)
        ]

        if not eligible_ids:
            logger.info("nyse_repair_no_eligible_artifacts")
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
                "nyse_repair_batch_committed",
                batch_size=updated,
                requeued_total=requeued
            )

        logger.info(
            "nyse_repair_completed",
            total_failed=total_failed,
            requeued=requeued,
            skipped=skipped
        )

        return (total_failed, requeued, skipped)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair failed NYSE artifacts by re-queuing them for download."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of artifacts to commit per batch (default: 100)"
    )

    args = parser.parse_args()

    total_failed, requeued, skipped = repair_failed_artifacts(batch_size=args.batch_size)
    logger.info(
        "nyse_repair_summary",
        total_failed=total_failed,
        requeued=requeued,
        skipped=skipped,
        batch_size=args.batch_size
    )


if __name__ == "__main__":
    main()
