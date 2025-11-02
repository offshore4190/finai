"""
Incremental Update Job
Scans last 7 days for new filings and triggers artifact downloads.
Includes retry logic for failed artifacts.
"""
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import structlog

from config.db import get_db_session
from config.settings import settings
from models import (
    Company, Filing, Artifact, ExecutionRun,
    IncrementalUpdate, RetryQueue
)
from services.sec_api import SECAPIClient
from services.storage import storage_service
from services.downloader import ArtifactDownloader
from utils import calculate_retry_delay

logger = structlog.get_logger()


class IncrementalUpdateJob:
    """Job for weekly incremental updates."""
    
    FORM_TYPES = ['10-K', '10-K/A', '10-Q', '10-Q/A']
    
    def __init__(self):
        """Initialize incremental job."""
        self.sec_client = SECAPIClient()
        self.downloader = ArtifactDownloader()
    
    def determine_fiscal_period(self, form_type: str, report_date: str) -> str:
        """Determine fiscal period from form type."""
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
    
    def scan_company_for_new_filings(
        self,
        session,
        company: Company,
        lookback_start: datetime,
        lookback_end: datetime
    ) -> int:
        """
        Scan a single company for new filings in date range.
        
        Args:
            session: Database session
            company: Company to scan
            lookback_start: Start date
            lookback_end: End date
        
        Returns:
            Number of new filings found
        """
        try:
            submissions = self.sec_client.fetch_company_submissions(company.cik)
            
            filings_data = self.sec_client.parse_filings(
                submissions,
                form_types=self.FORM_TYPES,
                start_date=lookback_start,
                end_date=lookback_end
            )
            
            new_filings = 0
            
            for filing_data in filings_data:
                # Check if already exists
                existing = session.query(Filing).filter(
                    Filing.accession_number == filing_data['accession_number']
                ).first()
                
                if existing:
                    continue
                
                # Create new filing
                fiscal_year = filing_data['filing_date'].year
                fiscal_period = self.determine_fiscal_period(
                    filing_data['form_type'],
                    filing_data.get('report_date')
                )
                
                filing = Filing(
                    company_id=company.id,
                    accession_number=filing_data['accession_number'],
                    form_type=filing_data['form_type'],
                    filing_date=filing_data['filing_date'],
                    report_date=filing_data.get('report_date'),
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    is_amendment=filing_data['is_amendment'],
                    primary_document=filing_data['primary_document']
                )
                session.add(filing)
                session.flush()
                
                # Ensure storage directory
                storage_service.ensure_directory_structure(
                    company.exchange,
                    company.ticker,
                    fiscal_year
                )
                
                # Create HTML artifact
                filing_date_str = filing.filing_date.strftime("%d-%m-%Y")
                html_path = storage_service.construct_path(
                    exchange=company.exchange,
                    ticker=company.ticker,
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    filing_date_str=filing_date_str,
                    artifact_type='html'
                )
                
                html_url = self.sec_client.construct_document_url(
                    company.cik,
                    filing.accession_number,
                    filing.primary_document
                )
                
                artifact = Artifact(
                    filing_id=filing.id,
                    artifact_type='html',
                    filename=filing.primary_document,
                    local_path=html_path,
                    url=html_url,
                    status='pending_download'
                )
                session.add(artifact)
                
                new_filings += 1
            
            session.commit()
            return new_filings
            
        except Exception as e:
            logger.error(
                "company_scan_failed",
                ticker=company.ticker,
                error=str(e)
            )
            return 0
    
    def download_pending_artifacts(
        self,
        session,
        execution_run_id: int,
        max_workers: int = 10
    ) -> tuple[int, int]:
        """
        Download all pending artifacts using thread pool.
        
        Args:
            session: Database session
            execution_run_id: Current execution run ID
            max_workers: Number of concurrent workers
        
        Returns:
            Tuple of (succeeded, failed) counts
        """
        # Get pending artifacts
        pending = session.query(Artifact).filter(
            Artifact.status == 'pending_download'
        ).all()
        
        logger.info("downloading_artifacts", count=len(pending))
        
        succeeded = 0
        failed = 0
        
        # Download in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self.downloader.download_artifact,
                    session,
                    artifact,
                    execution_run_id
                ): artifact for artifact in pending
            }
            
            for future in as_completed(futures):
                artifact = futures[future]
                try:
                    success = future.result()
                    if success:
                        succeeded += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(
                        "download_exception",
                        artifact_id=artifact.id,
                        error=str(e)
                    )
                    failed += 1
        
        return succeeded, failed
    
    def retry_failed_artifacts(self, session, execution_run_id: int) -> tuple[int, int]:
        """
        Retry artifacts that previously failed.
        
        Args:
            session: Database session
            execution_run_id: Current execution run ID
        
        Returns:
            Tuple of (succeeded, failed) counts
        """
        # Get artifacts eligible for retry
        retry_eligible = session.query(Artifact).filter(
            Artifact.status == 'failed',
            Artifact.retry_count < Artifact.max_retries
        ).all()
        
        logger.info("retrying_failed_artifacts", count=len(retry_eligible))
        
        succeeded = 0
        failed = 0
        
        for artifact in retry_eligible:
            success = self.downloader.download_artifact(
                session,
                artifact,
                execution_run_id
            )
            
            if success:
                succeeded += 1
            else:
                failed += 1
                
                # Schedule for next retry if not exhausted
                if artifact.retry_count < artifact.max_retries:
                    delay = calculate_retry_delay(artifact.retry_count)
                    scheduled_time = datetime.utcnow() + timedelta(seconds=delay)
                    
                    retry_entry = session.query(RetryQueue).filter(
                        RetryQueue.artifact_id == artifact.id
                    ).first()
                    
                    if retry_entry:
                        retry_entry.scheduled_for = scheduled_time
                    else:
                        retry_entry = RetryQueue(
                            artifact_id=artifact.id,
                            scheduled_for=scheduled_time
                        )
                        session.add(retry_entry)
        
        session.commit()
        return succeeded, failed
    
    def run(self):
        """Execute incremental update job."""
        logger.info("incremental_update_started")
        
        with get_db_session() as session:
            # Create execution run
            run = ExecutionRun(
                run_type='incremental',
                started_at=datetime.utcnow(),
                status='running'
            )
            session.add(run)
            session.commit()
            
            try:
                # Calculate lookback window
                lookback_end = datetime.utcnow()
                lookback_start = lookback_end - timedelta(days=settings.incremental_lookback_days)
                
                logger.info(
                    "incremental_window",
                    start=lookback_start.date(),
                    end=lookback_end.date()
                )
                
                # Get target companies (NASDAQ/NYSE family, excluding ETFs)
                # Corresponds to v_target_companies view
                # Query now ensures unique CIKs only (status='active')
                target_exchanges = ['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca']
                companies = session.query(Company).filter(
                    Company.status == 'active',
                    Company.is_active == True,
                    Company.exchange.in_(target_exchanges)
                ).all()

                logger.info("scanning_companies", count=len(companies), target_exchanges=target_exchanges)
                
                # Scan for new filings
                total_new_filings = 0
                for i, company in enumerate(companies, 1):
                    new_count = self.scan_company_for_new_filings(
                        session,
                        company,
                        lookback_start,
                        lookback_end
                    )
                    total_new_filings += new_count
                    
                    if i % 100 == 0:
                        logger.info(
                            "scan_progress",
                            processed=i,
                            total=len(companies),
                            new_filings=total_new_filings
                        )
                
                logger.info("scan_completed", new_filings=total_new_filings)
                
                # Download pending artifacts
                download_succeeded, download_failed = self.download_pending_artifacts(
                    session,
                    run.id,
                    max_workers=settings.max_workers
                )
                
                # Retry previously failed artifacts
                retry_succeeded, retry_failed = self.retry_failed_artifacts(
                    session,
                    run.id
                )
                
                # Calculate totals
                total_attempted = download_succeeded + download_failed + retry_succeeded + retry_failed
                total_succeeded = download_succeeded + retry_succeeded
                total_failed = download_failed + retry_failed
                
                # Update execution run
                run.completed_at = datetime.utcnow()
                run.status = 'completed'
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
                run.filings_discovered = total_new_filings
                run.artifacts_attempted = total_attempted
                run.artifacts_succeeded = total_succeeded
                run.artifacts_failed = total_failed
                
                # Calculate SLA metrics
                sla_duration_met = run.duration_seconds <= settings.sla_duration_seconds
                success_rate = (total_succeeded / total_attempted * 100) if total_attempted > 0 else 100.0
                sla_success_met = success_rate >= settings.sla_success_rate
                
                # Create incremental update record
                incremental = IncrementalUpdate(
                    execution_run_id=run.id,
                    lookback_start=lookback_start.date(),
                    lookback_end=lookback_end.date(),
                    companies_scanned=len(companies),
                    new_filings_found=total_new_filings,
                    sla_met=sla_duration_met and sla_success_met,
                    success_rate=round(success_rate, 2)
                )
                session.add(incremental)
                session.commit()
                
                logger.info(
                    "incremental_update_completed",
                    duration_seconds=run.duration_seconds,
                    new_filings=total_new_filings,
                    artifacts_succeeded=total_succeeded,
                    artifacts_failed=total_failed,
                    success_rate=success_rate,
                    sla_met=incremental.sla_met
                )
                
                # Alert if SLA not met
                if not incremental.sla_met:
                    logger.warning(
                        "sla_violation",
                        duration_ok=sla_duration_met,
                        success_rate_ok=sla_success_met,
                        duration_seconds=run.duration_seconds,
                        success_rate=success_rate
                    )
                
            except Exception as e:
                run.status = 'failed'
                run.error_summary = str(e)
                run.completed_at = datetime.utcnow()
                session.commit()
                
                logger.error("incremental_update_failed", error=str(e))
                raise


def main():
    """Main entry point."""
    job = IncrementalUpdateJob()
    job.run()


if __name__ == '__main__':
    main()
