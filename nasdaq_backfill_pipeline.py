#!/usr/bin/env python3
"""
NASDAQ Backfill Pipeline

Runs discovery, then keeps downloading/retrying pending artifacts until none remain.
This wraps the helper functions in nasdaq_full_backfill.py with a resilient loop.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Tuple

import structlog

from config.db import get_db_session
from models import Artifact, Company, Filing
from nasdaq_full_backfill import discover_filings, download_artifacts

logger = structlog.get_logger()

# Pipeline behaviour tuning constants.
MAX_DOWNLOAD_ROUNDS = 10          # Hard cap on download/retry cycles
SLEEP_BETWEEN_ROUNDS = 5          # Seconds to wait between download rounds


def pending_counts() -> Tuple[int, int, int]:
    """
    Return counts of pending, retryable failed, and terminal failed artifacts.

    Pending: status == 'pending_download'
    Retryable failed: status == 'failed' but retry_count < max_retries
    Terminal failed: status == 'failed' and retry_count >= max_retries
    """
    with get_db_session() as session:
        base_query = session.query(Artifact).join(
            Filing, Artifact.filing_id == Filing.id
        ).join(
            Company, Filing.company_id == Company.id
        ).filter(
            Company.exchange == 'NASDAQ'
        )

        pending = base_query.filter(Artifact.status == 'pending_download').count()
        retryable_failed = base_query.filter(
            Artifact.status == 'failed',
            Artifact.retry_count < Artifact.max_retries
        ).count()
        terminal_failed = base_query.filter(
            Artifact.status == 'failed',
            Artifact.retry_count >= Artifact.max_retries
        ).count()

        return pending, retryable_failed, terminal_failed


def requeue_retryable_failures() -> int:
    """
    Set retryable failed artifacts back to pending_download so the downloader will retry them.

    Returns:
        Number of artifacts requeued.
    """
    with get_db_session() as session:
        artifacts = session.query(Artifact).join(
            Filing, Artifact.filing_id == Filing.id
        ).join(
            Company, Filing.company_id == Company.id
        ).filter(
            Company.exchange == 'NASDAQ',
            Artifact.status == 'failed',
            Artifact.retry_count < Artifact.max_retries
        ).all()

        requeued = 0
        for artifact in artifacts:
            artifact.status = 'pending_download'
            requeued += 1

        if requeued:
            session.commit()

        return requeued


def run_pipeline():
    """Execute discovery followed by repeated download rounds until no work remains."""
    start_time = datetime.utcnow()
    logger.info("nasdaq_pipeline_started")

    filings_discovered, artifacts_created = discover_filings()

    logger.info(
        "nasdaq_discovery_summary",
        filings_discovered=filings_discovered,
        artifacts_created=artifacts_created
    )

    for round_idx in range(1, MAX_DOWNLOAD_ROUNDS + 1):
        logger.info("nasdaq_download_round_started", round=round_idx)

        succeeded, failed = download_artifacts()
        pending, retryable_failed, terminal_failed = pending_counts()

        logger.info(
            "nasdaq_download_round_completed",
            round=round_idx,
            succeeded=succeeded,
            failed=failed,
            pending=pending,
            retryable_failed=retryable_failed,
            terminal_failed=terminal_failed
        )

        if pending == 0 and retryable_failed == 0:
            logger.info(
                "nasdaq_pipeline_completed",
                rounds=round_idx,
                duration_seconds=int((datetime.utcnow() - start_time).total_seconds()),
                terminal_failed=terminal_failed
            )
            return

        if retryable_failed > 0:
            requeued = requeue_retryable_failures()
            logger.info("nasdaq_retryable_requeued", count=requeued)

        if round_idx < MAX_DOWNLOAD_ROUNDS:
            time.sleep(SLEEP_BETWEEN_ROUNDS)

    # If we exit the loop without returning, there is still work but we hit the round cap.
    pending, retryable_failed, terminal_failed = pending_counts()
    logger.warning(
        "nasdaq_pipeline_round_cap_reached",
        rounds=MAX_DOWNLOAD_ROUNDS,
        pending=pending,
        retryable_failed=retryable_failed,
        terminal_failed=terminal_failed
    )


def main():
    """CLI entry point."""
    try:
        run_pipeline()
    except KeyboardInterrupt:
        logger.info("nasdaq_pipeline_interrupted")
    except Exception as exc:
        logger.error("nasdaq_pipeline_failed", error=str(exc), exc_info=True)
        raise


if __name__ == "__main__":
    main()
