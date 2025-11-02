#!/usr/bin/env python3
"""
NASDAQ Full Backfill - Discovers and downloads all filings for NASDAQ companies.
This script processes all ~4,091 NASDAQ companies for 2023-2025 filings.
"""
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from config.db import get_db_session
from config.settings import settings
from models import Company, Filing, Artifact
from services.sec_api import SECAPIClient
from services.downloader import ArtifactDownloader
import structlog

logger = structlog.get_logger()

def discover_filings():
    """Discover all filings for NASDAQ companies (2023-2025)."""
    logger.info("nasdaq_backfill_started", phase="discovery")

    sec_client = SECAPIClient()

    with get_db_session() as session:
        # Get all NASDAQ companies
        companies = session.query(Company).filter(
            Company.exchange == 'NASDAQ'
        ).order_by(Company.ticker).all()

        total_companies = len(companies)
        logger.info("nasdaq_companies_loaded", count=total_companies)

        total_filings_found = 0
        total_artifacts_created = 0
        companies_processed = 0

        for i, company in enumerate(companies, 1):
            try:
                logger.info(
                    "processing_company",
                    progress=f"{i}/{total_companies}",
                    ticker=company.ticker,
                    cik=company.cik
                )

                # Fetch company submissions
                submissions = sec_client.fetch_company_submissions(company.cik)

                if not submissions:
                    logger.warning("no_submissions", ticker=company.ticker)
                    continue

                # Filter for 10-K and 10-Q filings from 2023-2025
                recent_filings = submissions.get('filings', {}).get('recent', {})

                forms = recent_filings.get('form', [])
                filing_dates = recent_filings.get('filingDate', [])
                accession_numbers = recent_filings.get('accessionNumber', [])
                primary_documents = recent_filings.get('primaryDocument', [])

                new_filings = 0

                for j in range(len(forms)):
                    form_type = forms[j]
                    filing_date_str = filing_dates[j]
                    accession_number = accession_numbers[j]
                    primary_doc = primary_documents[j] if j < len(primary_documents) else None

                    # Filter for 10-K and 10-Q only
                    if form_type not in ['10-K', '10-Q']:
                        continue

                    # Parse filing date
                    filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d').date()

                    # Filter for 2023-2025
                    if filing_date.year < 2023:
                        continue

                    # Check if filing already exists
                    existing = session.query(Filing).filter(
                        Filing.accession_number == accession_number
                    ).first()

                    if existing:
                        continue

                    # Determine fiscal year from filing date
                    fiscal_year = filing_date.year
                    if filing_date.month <= 3:
                        fiscal_year = filing_date.year

                    # Create new filing
                    filing = Filing(
                        company_id=company.id,
                        accession_number=accession_number,
                        form_type=form_type,
                        filing_date=filing_date,
                        fiscal_year=fiscal_year,
                        primary_document=primary_doc
                    )
                    session.add(filing)
                    session.flush()

                    # Create HTML artifact
                    if primary_doc:
                        clean_accession = accession_number.replace('-', '')
                        html_url = f"https://www.sec.gov/Archives/edgar/data/{company.cik}/{clean_accession}/{primary_doc}"

                        artifact = Artifact(
                            filing_id=filing.id,
                            artifact_type='html',
                            filename=primary_doc,
                            url=html_url,
                            status='pending_download'
                        )
                        session.add(artifact)
                        total_artifacts_created += 1

                    new_filings += 1

                if new_filings > 0:
                    session.commit()
                    total_filings_found += new_filings
                    logger.info(
                        "company_filings_processed",
                        ticker=company.ticker,
                        new_filings=new_filings,
                        total_so_far=total_filings_found
                    )

                companies_processed += 1

                # Progress checkpoint every 100 companies
                if companies_processed % 100 == 0:
                    logger.info(
                        "progress_checkpoint",
                        companies_processed=companies_processed,
                        total_companies=total_companies,
                        percentage=f"{(companies_processed/total_companies*100):.1f}%",
                        filings_found=total_filings_found,
                        artifacts_created=total_artifacts_created
                    )

            except Exception as e:
                logger.error(
                    "company_processing_failed",
                    ticker=company.ticker,
                    error=str(e),
                    exc_info=True
                )
                session.rollback()
                continue

        # Final summary
        logger.info(
            "nasdaq_backfill_discovery_completed",
            companies_processed=companies_processed,
            filings_discovered=total_filings_found,
            artifacts_created=total_artifacts_created
        )

        return total_filings_found, total_artifacts_created


def download_artifacts():
    """
    Download all pending artifacts for NASDAQ companies with concurrent workers.

    Uses session-per-thread pattern for thread safety:
    - Each worker thread creates its own database session
    - Each artifact commits independently (atomic operations)
    - Failures are isolated and don't affect successful downloads
    """
    logger.info(
        "nasdaq_download_started",
        phase="download",
        workers=settings.download_workers
    )

    # First, get artifact IDs (not full objects) from main session
    with get_db_session() as session:
        artifact_ids = session.query(Artifact.id).join(
            Filing, Artifact.filing_id == Filing.id
        ).join(
            Company, Filing.company_id == Company.id
        ).filter(
            Company.exchange == 'NASDAQ',
            Artifact.status == 'pending_download'
        ).order_by(
            Company.ticker, Filing.filing_date.desc()
        ).all()

        # Extract IDs from tuples
        artifact_ids = [aid[0] for aid in artifact_ids]
        total = len(artifact_ids)

    logger.info("nasdaq_artifacts_found", total=total, workers=settings.download_workers)

    if total == 0:
        logger.info("no_artifacts_to_download")
        return 0, 0

    # Define worker function with session-per-thread pattern
    def download_one(artifact_id):
        """
        Download a single artifact with its own database session.

        CRITICAL: Each thread creates its own session for thread safety.
        SQLAlchemy sessions are NOT thread-safe.
        """
        try:
            # Create independent session for this thread
            with get_db_session() as thread_session:
                # Fetch artifact in this thread's session
                artifact = thread_session.query(Artifact).get(artifact_id)

                if not artifact:
                    logger.warning("artifact_not_found", artifact_id=artifact_id)
                    return (artifact_id, False, "not_found")

                # Download using this thread's session
                downloader = ArtifactDownloader()
                success = downloader.download_artifact(thread_session, artifact)

                # Commit happens inside download_artifact
                # Session automatically closes when context exits

                status = artifact.status if artifact else "unknown"
                return (artifact_id, success, status)

        except Exception as e:
            logger.error(
                "artifact_download_error",
                artifact_id=artifact_id,
                error=str(e),
                exc_info=False  # Don't log full stack trace for each error
            )
            return (artifact_id, False, str(e))

    # Execute downloads with bounded concurrency
    logger.info(
        "starting_concurrent_downloads",
        total_artifacts=total,
        workers=settings.download_workers,
        estimated_duration_minutes=(total / (10 * settings.download_workers / 1.7))
    )

    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=settings.download_workers) as executor:
        # Submit all tasks and process as they complete
        future_to_id = {
            executor.submit(download_one, aid): aid
            for aid in artifact_ids
        }

        from concurrent.futures import as_completed
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
        "nasdaq_download_completed",
        total=total,
        succeeded=succeeded,
        failed=failed,
        success_rate=f"{(succeeded/total*100):.1f}%" if total > 0 else "0%",
        workers=settings.download_workers
    )

    return succeeded, failed


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='NASDAQ Full Backfill - Discover and download all filings'
    )
    parser.add_argument(
        '--discover-only',
        action='store_true',
        help='Only discover filings, do not download'
    )
    parser.add_argument(
        '--download-only',
        action='store_true',
        help='Only download pending artifacts'
    )

    args = parser.parse_args()

    try:
        start_time = datetime.now()

        if args.download_only:
            logger.info("mode", operation="download_only")
            succeeded, failed = download_artifacts()
        elif args.discover_only:
            logger.info("mode", operation="discover_only")
            filings, artifacts = discover_filings()
        else:
            logger.info("mode", operation="full_backfill")
            # Full backfill: discover then download
            filings, artifacts = discover_filings()
            succeeded, failed = download_artifacts()

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            "nasdaq_backfill_completed",
            duration_seconds=duration,
            duration_hours=f"{duration/3600:.2f}"
        )

    except KeyboardInterrupt:
        logger.info("nasdaq_backfill_interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error("nasdaq_backfill_failed", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
