#!/usr/bin/env python3
"""
Targeted download script for test companies.
Downloads pending artifacts for specific companies only.
"""
import sys
from config.db import get_db_session
from models import Company, Filing, Artifact
from services.downloader import ArtifactDownloader
import structlog

logger = structlog.get_logger()

# Test companies
TEST_TICKERS = ['DHR', 'GILD', 'HON', 'KLAC', 'LOW']

def main():
    """Download artifacts for test companies only."""
    logger.info("starting_targeted_download", tickers=TEST_TICKERS)

    downloader = ArtifactDownloader()

    with get_db_session() as session:
        # Get all pending artifacts for test companies
        artifacts = session.query(Artifact).join(
            Filing, Artifact.filing_id == Filing.id
        ).join(
            Company, Filing.company_id == Company.id
        ).filter(
            Company.ticker.in_(TEST_TICKERS),
            Artifact.status == 'pending_download'
        ).order_by(
            Company.ticker, Filing.filing_date.desc()
        ).all()

        total = len(artifacts)
        logger.info("artifacts_found", total=total, tickers=TEST_TICKERS)

        if total == 0:
            logger.info("no_artifacts_to_download")
            return

        # Download each artifact
        succeeded = 0
        failed = 0

        for i, artifact in enumerate(artifacts, 1):
            filing = artifact.filing
            company = filing.company

            logger.info(
                "downloading_artifact",
                progress=f"{i}/{total}",
                ticker=company.ticker,
                form_type=filing.form_type,
                artifact_type=artifact.artifact_type,
                filename=artifact.filename
            )

            try:
                success = downloader.download_artifact(session, artifact)
                if success:
                    succeeded += 1
                    logger.info(
                        "artifact_downloaded",
                        progress=f"{i}/{total}",
                        ticker=company.ticker,
                        filename=artifact.filename,
                        status="success"
                    )
                else:
                    failed += 1
                    logger.warning(
                        "artifact_download_failed",
                        progress=f"{i}/{total}",
                        ticker=company.ticker,
                        filename=artifact.filename
                    )
            except Exception as e:
                failed += 1
                logger.error(
                    "artifact_download_error",
                    progress=f"{i}/{total}",
                    ticker=company.ticker,
                    error=str(e)
                )

        # Final summary
        logger.info(
            "targeted_download_completed",
            total=total,
            succeeded=succeeded,
            failed=failed,
            success_rate=f"{(succeeded/total*100):.1f}%" if total > 0 else "0%"
        )

        # Show summary by company
        for ticker in TEST_TICKERS:
            company = session.query(Company).filter(Company.ticker == ticker).first()
            if company:
                downloaded_count = session.query(Artifact).join(
                    Filing
                ).filter(
                    Filing.company_id == company.id,
                    Artifact.status == 'downloaded'
                ).count()

                pending_count = session.query(Artifact).join(
                    Filing
                ).filter(
                    Filing.company_id == company.id,
                    Artifact.status == 'pending_download'
                ).count()

                logger.info(
                    "company_summary",
                    ticker=ticker,
                    downloaded=downloaded_count,
                    pending=pending_count
                )

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("download_interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error("download_failed", error=str(e), exc_info=True)
        sys.exit(1)
