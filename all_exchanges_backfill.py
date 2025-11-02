#!/usr/bin/env python3
"""
All Exchanges Backfill - Discovers and downloads all filings for all exchanges.
This script processes companies from all exchanges (NASDAQ, NYSE, etc.) for 2023-2025 filings.
Optimized for speed and accuracy with parallel processing support.
"""
import sys
from datetime import datetime
from config.db import get_db_session
from models import Company, Filing, Artifact
from services.sec_api import SECAPIClient
from services.downloader import ArtifactDownloader
import structlog

logger = structlog.get_logger()

def discover_filings(exchange=None):
    """Discover all filings for companies (2023-2025).

    Args:
        exchange: If specified, only process this exchange. Otherwise process all.
    """
    logger.info("backfill_started", phase="discovery", exchange=exchange or "ALL")

    sec_client = SECAPIClient()

    with get_db_session() as session:
        # Get companies for specified exchange or all
        query = session.query(Company)
        if exchange:
            query = query.filter(Company.exchange == exchange)

        companies = query.order_by(Company.exchange, Company.ticker).all()

        total_companies = len(companies)
        logger.info("companies_loaded", count=total_companies, exchange=exchange or "ALL")

        total_filings_found = 0
        total_artifacts_created = 0
        companies_processed = 0
        exchange_stats = {}

        for i, company in enumerate(companies, 1):
            try:
                logger.info(
                    "processing_company",
                    progress=f"{i}/{total_companies}",
                    ticker=company.ticker,
                    exchange=company.exchange,
                    cik=company.cik
                )

                # Fetch company submissions
                submissions = sec_client.fetch_company_submissions(company.cik)

                if not submissions:
                    logger.warning("no_submissions", ticker=company.ticker, exchange=company.exchange)
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

                    # Track stats per exchange
                    if company.exchange not in exchange_stats:
                        exchange_stats[company.exchange] = {'companies': 0, 'filings': 0}
                    exchange_stats[company.exchange]['companies'] += 1
                    exchange_stats[company.exchange]['filings'] += new_filings

                    logger.info(
                        "company_filings_processed",
                        ticker=company.ticker,
                        exchange=company.exchange,
                        new_filings=new_filings,
                        total_so_far=total_filings_found
                    )

                companies_processed += 1

                # Progress checkpoint every 50 companies
                if companies_processed % 50 == 0:
                    logger.info(
                        "progress_checkpoint",
                        companies_processed=companies_processed,
                        total_companies=total_companies,
                        percentage=f"{(companies_processed/total_companies*100):.1f}%",
                        filings_found=total_filings_found,
                        artifacts_created=total_artifacts_created,
                        exchange_stats=exchange_stats
                    )

            except Exception as e:
                logger.error(
                    "company_processing_failed",
                    ticker=company.ticker,
                    exchange=company.exchange,
                    error=str(e),
                    exc_info=True
                )
                session.rollback()
                continue

        # Final summary
        logger.info(
            "backfill_discovery_completed",
            exchange=exchange or "ALL",
            companies_processed=companies_processed,
            filings_discovered=total_filings_found,
            artifacts_created=total_artifacts_created,
            exchange_stats=exchange_stats
        )

        return total_filings_found, total_artifacts_created


def download_artifacts(exchange=None):
    """Download all pending artifacts.

    Args:
        exchange: If specified, only download for this exchange. Otherwise download all.
    """
    logger.info("download_started", phase="download", exchange=exchange or "ALL")

    downloader = ArtifactDownloader()

    with get_db_session() as session:
        # Get all pending artifacts
        query = session.query(Artifact).join(
            Filing, Artifact.filing_id == Filing.id
        ).join(
            Company, Filing.company_id == Company.id
        ).filter(
            Artifact.status == 'pending_download'
        )

        if exchange:
            query = query.filter(Company.exchange == exchange)

        artifacts = query.order_by(
            Company.exchange, Company.ticker, Filing.filing_date.desc()
        ).all()

        total = len(artifacts)
        logger.info("artifacts_found", total=total, exchange=exchange or "ALL")

        if total == 0:
            logger.info("no_artifacts_to_download")
            return 0, 0

        succeeded = 0
        failed = 0
        exchange_stats = {}

        for i, artifact in enumerate(artifacts, 1):
            filing = artifact.filing
            company = filing.company

            if i % 100 == 0 or i == 1:
                logger.info(
                    "download_progress",
                    progress=f"{i}/{total}",
                    percentage=f"{(i/total*100):.1f}%",
                    succeeded=succeeded,
                    failed=failed,
                    current_ticker=company.ticker,
                    current_exchange=company.exchange
                )

            try:
                success = downloader.download_artifact(session, artifact)

                # Track stats per exchange
                if company.exchange not in exchange_stats:
                    exchange_stats[company.exchange] = {'succeeded': 0, 'failed': 0}

                if success:
                    succeeded += 1
                    exchange_stats[company.exchange]['succeeded'] += 1
                else:
                    failed += 1
                    exchange_stats[company.exchange]['failed'] += 1

            except Exception as e:
                failed += 1
                if company.exchange not in exchange_stats:
                    exchange_stats[company.exchange] = {'succeeded': 0, 'failed': 0}
                exchange_stats[company.exchange]['failed'] += 1

                logger.error(
                    "artifact_download_error",
                    progress=f"{i}/{total}",
                    ticker=company.ticker,
                    exchange=company.exchange,
                    error=str(e)
                )

        # Final summary
        logger.info(
            "download_completed",
            exchange=exchange or "ALL",
            total=total,
            succeeded=succeeded,
            failed=failed,
            success_rate=f"{(succeeded/total*100):.1f}%" if total > 0 else "0%",
            exchange_stats=exchange_stats
        )

        return succeeded, failed


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='All Exchanges Backfill - Discover and download all filings'
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
    parser.add_argument(
        '--exchange',
        type=str,
        choices=['NASDAQ', 'NYSE', 'AMEX', 'OTC'],
        help='Process only specified exchange'
    )

    args = parser.parse_args()

    try:
        start_time = datetime.now()

        exchange_name = args.exchange or "ALL"

        if args.download_only:
            logger.info("mode", operation="download_only", exchange=exchange_name)
            succeeded, failed = download_artifacts(args.exchange)
        elif args.discover_only:
            logger.info("mode", operation="discover_only", exchange=exchange_name)
            filings, artifacts = discover_filings(args.exchange)
        else:
            logger.info("mode", operation="full_backfill", exchange=exchange_name)
            # Full backfill: discover then download
            filings, artifacts = discover_filings(args.exchange)
            succeeded, failed = download_artifacts(args.exchange)

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            "backfill_completed",
            exchange=exchange_name,
            duration_seconds=duration,
            duration_hours=f"{duration/3600:.2f}"
        )

    except KeyboardInterrupt:
        logger.info("backfill_interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error("backfill_failed", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
