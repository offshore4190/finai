#!/usr/bin/env python3
"""
Concurrent Backfill Job
Discovers filings and downloads artifacts in parallel with real-time progress tracking.
Major improvements:
- Parallel company processing (respects rate limits)
- Concurrent discovery + downloads
- Real-time progress dashboard
- Resume capability
- Much faster performance
"""

import asyncio
import time
from datetime import datetime
from typing import List, Optional, Set
from collections import defaultdict
from pathlib import Path

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from config.db import get_db_session, engine
from config.settings import settings
from models import Company, Filing, Artifact, ExecutionRun
from services.sec_api import SECAPIClient
from services.downloader import ArtifactDownloader

logger = structlog.get_logger()


class ConcurrentBackfillJob:
    """Concurrent backfill with discovery + download."""

    FORM_TYPES = ['10-K', '10-K/A', '10-Q', '10-Q/A']
    START_DATE = datetime(2023, 1, 1)
    END_DATE = datetime(2025, 12, 31)

    def __init__(
        self,
        max_concurrent_companies: int = 10,
        max_concurrent_downloads: int = 5,
        download_as_discover: bool = True,
        exchanges: List[str] = None
    ):
        """
        Initialize concurrent backfill job.

        Args:
            max_concurrent_companies: How many companies to process in parallel
            max_concurrent_downloads: How many artifacts to download concurrently
            download_as_discover: Start downloads immediately as artifacts are discovered
            exchanges: Filter by specific exchanges (None = all)
        """
        self.sec_client = SECAPIClient()
        self.downloader = ArtifactDownloader()
        self.max_concurrent_companies = max_concurrent_companies
        self.max_concurrent_downloads = max_concurrent_downloads
        self.download_as_discover = download_as_discover
        self.exchanges = exchanges or ['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca']

        # Progress tracking
        self.stats = {
            'companies_processed': 0,
            'companies_with_new_filings': 0,
            'filings_discovered': 0,
            'artifacts_created': 0,
            'artifacts_downloaded': 0,
            'artifacts_failed': 0,
            'errors': []
        }
        self.start_time = None
        self.companies_in_progress: Set[str] = set()

    def determine_fiscal_period(self, form_type: str, report_date: str) -> str:
        """Determine fiscal period from form type and report date."""
        if '10-K' in form_type:
            return 'FY'

        if report_date:
            month = int(report_date.split('-')[1])
            if month in [1, 2, 3]:
                return 'Q1'
            elif month in [4, 5, 6]:
                return 'Q2'
            elif month in [7, 8, 9]:
                return 'Q3'
            else:
                return 'Q4'

        return 'Q4'

    async def process_company(self, company_info: dict, run_id: int) -> dict:
        """
        Process a single company: discover filings and optionally download.

        Args:
            company_info: Dict with company details
            run_id: Execution run ID

        Returns:
            Dict with results
        """
        ticker = company_info['ticker']
        cik = company_info['cik']
        company_id = company_info['id']

        self.companies_in_progress.add(ticker)

        try:
            # Fetch submissions from SEC
            loop = asyncio.get_event_loop()
            submissions = await loop.run_in_executor(
                None,
                self.sec_client.fetch_company_submissions,
                cik
            )

            # Parse filings
            filings_data = self.sec_client.parse_filings(
                submissions,
                form_types=self.FORM_TYPES,
                start_date=self.START_DATE,
                end_date=self.END_DATE
            )

            if not filings_data:
                return {
                    'ticker': ticker,
                    'success': True,
                    'new_filings': 0,
                    'artifacts_created': 0
                }

            # Process in database session
            new_filings = 0
            artifacts_created = 0
            artifact_ids_to_download = []

            with get_db_session() as session:
                for filing_data in filings_data:
                    # Check if filing exists
                    existing = session.query(Filing).filter(
                        Filing.accession_number == filing_data['accession_number']
                    ).first()

                    if existing:
                        continue

                    # Determine fiscal year and period
                    fiscal_year = filing_data['filing_date'].year
                    report_date = filing_data.get('report_date')

                    # Convert report_date to string if it's a datetime object
                    report_date_str = None
                    if report_date:
                        if isinstance(report_date, str):
                            report_date_str = report_date
                        else:
                            report_date_str = report_date.strftime('%Y-%m-%d')

                    fiscal_period = self.determine_fiscal_period(
                        filing_data['form_type'],
                        report_date_str
                    )

                    # Create filing record
                    filing = Filing(
                        company_id=company_id,
                        accession_number=filing_data['accession_number'],
                        form_type=filing_data['form_type'],
                        filing_date=filing_data['filing_date'],
                        report_date=report_date,
                        fiscal_year=fiscal_year,
                        fiscal_period=fiscal_period,
                        primary_document=filing_data.get('primary_document'),
                        document_count=filing_data.get('document_count', 0),
                        is_amendment=filing_data.get('is_amendment', False)
                    )
                    session.add(filing)
                    session.flush()  # Get filing.id

                    # Create artifact for primary HTML document
                    primary_doc = filing_data.get('primary_document')
                    if primary_doc:
                        accession_no_dashes = filing_data['accession_number'].replace('-', '')
                        html_url = (
                            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                            f"{accession_no_dashes}/{primary_doc}"
                        )

                        artifact = Artifact(
                            filing_id=filing.id,
                            artifact_type='html',
                            filename=primary_doc,
                            url=html_url,
                            status='pending_download'
                        )
                        session.add(artifact)
                        session.flush()  # Get artifact.id

                        artifact_ids_to_download.append(artifact.id)
                        artifacts_created += 1

                    new_filings += 1

                session.commit()

            # Update stats
            self.stats['companies_processed'] += 1
            if new_filings > 0:
                self.stats['companies_with_new_filings'] += 1
            self.stats['filings_discovered'] += new_filings
            self.stats['artifacts_created'] += artifacts_created

            # Download artifacts immediately if enabled
            if self.download_as_discover and artifact_ids_to_download:
                await self.download_artifacts(artifact_ids_to_download)

            logger.info(
                "company_processed",
                ticker=ticker,
                new_filings=new_filings,
                artifacts_created=artifacts_created
            )

            return {
                'ticker': ticker,
                'success': True,
                'new_filings': new_filings,
                'artifacts_created': artifacts_created
            }

        except Exception as e:
            error_msg = f"{ticker}: {str(e)}"
            self.stats['errors'].append(error_msg)
            logger.error(
                "company_processing_failed",
                ticker=ticker,
                cik=cik,
                error=str(e)
            )
            return {
                'ticker': ticker,
                'success': False,
                'error': str(e)
            }
        finally:
            self.companies_in_progress.discard(ticker)

    async def download_artifacts(self, artifact_ids: List[int]):
        """
        Download artifacts concurrently.

        Args:
            artifact_ids: List of artifact IDs to download
        """
        semaphore = asyncio.Semaphore(self.max_concurrent_downloads)

        async def download_one(artifact_id: int):
            async with semaphore:
                try:
                    with get_db_session() as session:
                        artifact = session.query(Artifact).filter_by(id=artifact_id).first()
                        if not artifact or artifact.status != 'pending_download':
                            return

                        # Download synchronously but in executor
                        loop = asyncio.get_event_loop()
                        success = await loop.run_in_executor(
                            None,
                            self.downloader.download_artifact,
                            session,
                            artifact
                        )

                        if success or artifact.status in ('downloaded', 'skipped'):
                            self.stats['artifacts_downloaded'] += 1
                        else:
                            self.stats['artifacts_failed'] += 1

                except Exception as e:
                    self.stats['artifacts_failed'] += 1
                    logger.error("artifact_download_failed", artifact_id=artifact_id, error=str(e))

        # Download all artifacts concurrently (with semaphore limit)
        await asyncio.gather(*[download_one(aid) for aid in artifact_ids])

    async def process_batch(self, companies: List[dict], run_id: int):
        """
        Process a batch of companies concurrently.

        Args:
            companies: List of company info dicts
            run_id: Execution run ID
        """
        semaphore = asyncio.Semaphore(self.max_concurrent_companies)

        async def process_with_semaphore(company_info):
            async with semaphore:
                return await self.process_company(company_info, run_id)

        # Process all companies in batch concurrently
        results = await asyncio.gather(
            *[process_with_semaphore(c) for c in companies],
            return_exceptions=True
        )

        return results

    def print_progress(self, total_companies: int):
        """Print progress dashboard."""
        if not self.start_time:
            return

        elapsed = time.time() - self.start_time
        rate = self.stats['companies_processed'] / elapsed if elapsed > 0 else 0
        remaining = total_companies - self.stats['companies_processed']
        eta_seconds = remaining / rate if rate > 0 else 0

        print("\n" + "=" * 80)
        print(f"CONCURRENT BACKFILL PROGRESS")
        print("=" * 80)
        print(f"Elapsed Time:     {int(elapsed)}s ({int(elapsed/60)}m {int(elapsed%60)}s)")
        print(f"Processing Rate:  {rate:.1f} companies/sec")
        print(f"ETA:              {int(eta_seconds/60)}m {int(eta_seconds%60)}s")
        print()
        print(f"Companies:        {self.stats['companies_processed']:,}/{total_companies:,} "
              f"({self.stats['companies_processed']*100/total_companies:.1f}%)")
        print(f"With New Data:    {self.stats['companies_with_new_filings']:,}")
        print(f"In Progress:      {len(self.companies_in_progress)} companies")
        print()
        print(f"Filings Found:    {self.stats['filings_discovered']:,}")
        print(f"Artifacts:        {self.stats['artifacts_created']:,} created")
        print(f"Downloads:        {self.stats['artifacts_downloaded']:,} success, "
              f"{self.stats['artifacts_failed']:,} failed")

        if self.stats['errors']:
            print(f"\nRecent Errors ({len(self.stats['errors'])} total):")
            for err in self.stats['errors'][-5:]:
                print(f"  - {err}")

        print("=" * 80)

    async def run_async(self, batch_size: int = 100, progress_interval: int = 30):
        """
        Run backfill job asynchronously.

        Args:
            batch_size: Number of companies per batch
            progress_interval: Seconds between progress updates
        """
        logger.info(
            "concurrent_backfill_started",
            max_concurrent_companies=self.max_concurrent_companies,
            max_concurrent_downloads=self.max_concurrent_downloads,
            download_as_discover=self.download_as_discover
        )

        self.start_time = time.time()

        with get_db_session() as session:
            # Create execution run
            run = ExecutionRun(
                run_type='backfill_concurrent',
                started_at=datetime.utcnow(),
                status='running',
                metadata={
                    'start_date': str(self.START_DATE),
                    'end_date': str(self.END_DATE),
                    'max_concurrent_companies': self.max_concurrent_companies,
                    'max_concurrent_downloads': self.max_concurrent_downloads,
                    'exchanges': self.exchanges
                }
            )
            session.add(run)
            session.commit()
            run_id = run.id

        try:
            # Get companies without filings (prioritize these)
            with get_db_session() as session:
                # Companies without any filings
                companies_no_filings = session.query(Company).filter(
                    Company.is_active == True,
                    Company.exchange.in_(self.exchanges),
                    ~Company.id.in_(
                        session.query(Filing.company_id).distinct()
                    )
                ).all()

                # Companies with filings (check for missing data)
                companies_with_filings = session.query(Company).filter(
                    Company.is_active == True,
                    Company.exchange.in_(self.exchanges),
                    Company.id.in_(
                        session.query(Filing.company_id).distinct()
                    )
                ).all()

                # Prioritize: companies without filings first
                all_companies = companies_no_filings + companies_with_filings

                company_list = [
                    {'id': c.id, 'ticker': c.ticker, 'cik': c.cik, 'exchange': c.exchange}
                    for c in all_companies
                ]

            total_companies = len(company_list)
            logger.info(
                "companies_loaded",
                total=total_companies,
                without_filings=len(companies_no_filings),
                with_filings=len(companies_with_filings)
            )

            # Process in batches
            last_progress = time.time()

            for i in range(0, total_companies, batch_size):
                batch = company_list[i:i+batch_size]

                # Process batch
                await self.process_batch(batch, run_id)

                # Print progress
                if time.time() - last_progress >= progress_interval:
                    self.print_progress(total_companies)
                    last_progress = time.time()

            # Final progress
            self.print_progress(total_companies)

            # Update execution run
            with get_db_session() as session:
                run = session.query(ExecutionRun).filter_by(id=run_id).first()
                run.completed_at = datetime.utcnow()
                run.status = 'completed'
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
                run.filings_discovered = self.stats['filings_discovered']

                # Update metadata by creating new dict (JSONB column requires full replacement)
                updated_metadata = run.metadata.copy() if run.metadata else {}
                updated_metadata['stats'] = self.stats
                run.metadata = updated_metadata
                session.commit()

            logger.info(
                "concurrent_backfill_completed",
                companies_processed=self.stats['companies_processed'],
                filings_discovered=self.stats['filings_discovered'],
                artifacts_downloaded=self.stats['artifacts_downloaded'],
                duration_seconds=int(time.time() - self.start_time)
            )

        except Exception as e:
            with get_db_session() as session:
                run = session.query(ExecutionRun).filter_by(id=run_id).first()
                run.status = 'failed'
                run.error_summary = str(e)
                run.completed_at = datetime.utcnow()
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())

                # Update metadata with stats at time of failure
                updated_metadata = run.metadata.copy() if run.metadata else {}
                updated_metadata['stats'] = self.stats
                run.metadata = updated_metadata
                session.commit()

            logger.error("concurrent_backfill_failed", error=str(e))
            raise

    def run(self, batch_size: int = 100, progress_interval: int = 30):
        """Synchronous wrapper for async run."""
        asyncio.run(self.run_async(batch_size, progress_interval))


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Concurrent backfill with discovery + downloads')
    parser.add_argument(
        '--max-concurrent-companies',
        type=int,
        default=10,
        help='Max companies to process concurrently (default: 10)'
    )
    parser.add_argument(
        '--max-concurrent-downloads',
        type=int,
        default=5,
        help='Max artifacts to download concurrently (default: 5)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Companies per batch (default: 100)'
    )
    parser.add_argument(
        '--progress-interval',
        type=int,
        default=30,
        help='Seconds between progress updates (default: 30)'
    )
    parser.add_argument(
        '--no-download',
        action='store_true',
        help='Discover only, do not download artifacts'
    )
    parser.add_argument(
        '--exchange',
        action='append',
        help='Filter by exchange (can specify multiple)'
    )

    args = parser.parse_args()

    job = ConcurrentBackfillJob(
        max_concurrent_companies=args.max_concurrent_companies,
        max_concurrent_downloads=args.max_concurrent_downloads,
        download_as_discover=not args.no_download,
        exchanges=args.exchange if args.exchange else None
    )

    job.run(
        batch_size=args.batch_size,
        progress_interval=args.progress_interval
    )


if __name__ == '__main__':
    main()
