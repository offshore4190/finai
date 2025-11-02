#!/usr/bin/env python3
"""
Universal Download Script
Downloads all pending artifacts across all exchanges with concurrent workers.
"""
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import structlog

from config.db import get_db_session
from config.settings import settings
from models import Artifact
from services.downloader import ArtifactDownloader

logger = structlog.get_logger()


def download_all_pending(workers: int = 8):
    """
    Download all pending artifacts across all exchanges.

    Args:
        workers: Number of concurrent download workers
    """
    logger.info("universal_download_started", phase="download", workers=workers)

    # Get artifact IDs (not full objects) from main session
    with get_db_session() as session:
        artifact_ids = session.query(Artifact.id).filter(
            Artifact.status == 'pending_download'
        ).order_by(Artifact.id).all()

        # Extract IDs from tuples
        artifact_ids = [aid[0] for aid in artifact_ids]
        total = len(artifact_ids)

    logger.info("pending_artifacts_found", total=total, workers=workers)

    if total == 0:
        logger.info("no_artifacts_to_download")
        return 0, 0

    # Define worker function with session-per-thread pattern
    def download_one(artifact_id):
        """
        Download a single artifact with its own database session.

        CRITICAL: Each thread creates its own session for thread safety.
        """
        try:
            # Create independent session for this thread
            with get_db_session() as thread_session:
                # Fetch artifact in this thread's session
                artifact = thread_session.query(Artifact).filter_by(id=artifact_id).first()

                if not artifact:
                    logger.warning("artifact_not_found", artifact_id=artifact_id)
                    return (artifact_id, False, "not_found")

                # Download using this thread's session
                downloader = ArtifactDownloader()
                success = downloader.download_artifact(thread_session, artifact)

                status = artifact.status if artifact else "unknown"
                return (artifact_id, success, status)

        except Exception as e:
            logger.error(
                "artifact_download_error",
                artifact_id=artifact_id,
                error=str(e),
                exc_info=False
            )
            return (artifact_id, False, str(e))

    # Execute downloads with bounded concurrency
    logger.info(
        "starting_concurrent_downloads",
        total_artifacts=total,
        workers=workers,
        estimated_duration_minutes=(total / (10 * workers / 1.7))
    )

    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Submit all tasks and process as they complete
        future_to_id = {
            executor.submit(download_one, aid): aid
            for aid in artifact_ids
        }

        for future in as_completed(future_to_id):
            result = future.result()
            results.append(result)
            completed += 1

            # Log progress periodically
            if completed % 100 == 0 or completed == 1:
                succeeded = sum(1 for _, success, _ in results if success)
                failed = completed - succeeded
                logger.info(
                    "download_progress",
                    progress=f"{completed}/{total}",
                    percentage=f"{(completed/total*100):.1f}%",
                    succeeded=succeeded,
                    failed=failed
                )

    # Aggregate final results
    succeeded = sum(1 for _, success, _ in results if success)
    failed = total - succeeded

    # Final summary
    logger.info(
        "universal_download_completed",
        total=total,
        succeeded=succeeded,
        failed=failed,
        success_rate=f"{(succeeded/total*100):.1f}%" if total > 0 else "0%",
        workers=workers
    )

    return succeeded, failed


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Download all pending artifacts across all exchanges'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=8,
        help='Number of concurrent download workers (default: 8)'
    )

    args = parser.parse_args()

    try:
        start_time = datetime.now()

        succeeded, failed = download_all_pending(workers=args.workers)

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            "download_session_completed",
            duration_seconds=duration,
            duration_minutes=f"{duration/60:.2f}"
        )

    except KeyboardInterrupt:
        logger.info("download_interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error("download_failed", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
