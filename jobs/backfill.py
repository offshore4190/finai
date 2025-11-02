"""
Backfill Job
Fetches all 10-K and 10-Q filings for 2023-2025.
"""
from datetime import datetime
from typing import List

import structlog

from config.db import get_db_session
from config.settings import settings
from models import Company, Filing, Artifact, ExecutionRun
from services.sec_api import SECAPIClient
from services.storage import storage_service

logger = structlog.get_logger()


class BackfillJob:
    """Job to backfill historical filings."""
    
    FORM_TYPES = ['10-K', '10-K/A', '10-Q', '10-Q/A']
    START_DATE = datetime(2023, 1, 1)
    END_DATE = datetime(2025, 12, 31)
    
    def __init__(self, limit: int = None):
        """
        Initialize backfill job.
        
        Args:
            limit: Maximum number of companies to process (for testing)
        """
        self.sec_client = SECAPIClient()
        self.limit = limit
    
    def determine_fiscal_period(self, form_type: str, report_date: str) -> str:
        """
        Determine fiscal period from form type and report date.
        
        Args:
            form_type: Form type (10-K or 10-Q)
            report_date: Report date string (YYYY-MM-DD)
        
        Returns:
            Fiscal period: 'FY', 'Q1', 'Q2', 'Q3', or 'Q4'
        """
        if '10-K' in form_type:
            return 'FY'
        
        # For 10-Q, determine quarter from month
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
        
        return 'Q4'  # Default
    
    def process_company_filings(self, session, company: Company, run_id: int) -> int:
        """
        Process filings for a single company.
        
        Args:
            session: Database session
            company: Company object
            run_id: Execution run ID
        
        Returns:
            Number of new filings discovered
        """
        try:
            # Fetch submissions
            submissions = self.sec_client.fetch_company_submissions(company.cik)
            
            # Parse filings
            filings_data = self.sec_client.parse_filings(
                submissions,
                form_types=self.FORM_TYPES,
                start_date=self.START_DATE,
                end_date=self.END_DATE
            )
            
            new_filings = 0
            
            for filing_data in filings_data:
                # Check if filing already exists
                existing = session.query(Filing).filter(
                    Filing.accession_number == filing_data['accession_number']
                ).first()
                
                if existing:
                    continue
                
                # Determine fiscal year and period
                fiscal_year = filing_data['filing_date'].year
                fiscal_period = self.determine_fiscal_period(
                    filing_data['form_type'],
                    filing_data.get('report_date')
                )
                
                # Create filing record
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
                session.flush()  # Get filing ID
                
                # Ensure storage directory exists
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
            
            logger.info(
                "company_filings_processed",
                ticker=company.ticker,
                cik=company.cik,
                new_filings=new_filings
            )
            
            return new_filings
            
        except Exception as e:
            logger.error(
                "company_processing_failed",
                ticker=company.ticker,
                cik=company.cik,
                error=str(e)
            )
            return 0
    
    def run(self):
        """Execute backfill job."""
        logger.info("backfill_started", start_date=self.START_DATE, end_date=self.END_DATE)
        
        with get_db_session() as session:
            # Create execution run
            run = ExecutionRun(
                run_type='backfill',
                started_at=datetime.utcnow(),
                status='running',
                meta_data={'start_date': str(self.START_DATE), 'end_date': str(self.END_DATE)}
            )
            session.add(run)
            session.commit()
            
            try:
                # Get target companies (NASDAQ/NYSE family, excluding ETFs)
                # Corresponds to v_target_companies view
                # Query now ensures unique CIKs only (status='active' enforced by partial index)
                target_exchanges = ['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca']
                query = session.query(Company).filter(
                    Company.status == 'active',
                    Company.is_active == True,
                    Company.exchange.in_(target_exchanges)
                )
                if self.limit:
                    query = query.limit(self.limit)

                companies = query.all()

                # Verify uniqueness (should always pass after migration 005)
                ciks = [c.cik for c in companies]
                assert len(ciks) == len(set(ciks)), "Duplicate CIKs found in query results - migration 005 may not have run"

                logger.info("backfill_companies_loaded", count=len(companies), target_exchanges=target_exchanges)
                
                total_filings = 0
                
                for i, company in enumerate(companies, 1):
                    logger.info(
                        "processing_company",
                        progress=f"{i}/{len(companies)}",
                        ticker=company.ticker
                    )
                    
                    filings_count = self.process_company_filings(session, company, run.id)
                    total_filings += filings_count
                    
                    # Progress update every 100 companies
                    if i % 100 == 0:
                        logger.info(
                            "backfill_progress",
                            companies_processed=i,
                            total_companies=len(companies),
                            filings_discovered=total_filings
                        )
                
                # Update execution run
                run.completed_at = datetime.utcnow()
                run.status = 'completed'
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
                run.filings_discovered = total_filings
                session.commit()
                
                logger.info(
                    "backfill_completed",
                    companies_processed=len(companies),
                    filings_discovered=total_filings,
                    duration_seconds=run.duration_seconds
                )
                
            except Exception as e:
                run.status = 'failed'
                run.error_summary = str(e)
                run.completed_at = datetime.utcnow()
                session.commit()
                
                logger.error("backfill_failed", error=str(e))
                raise


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Backfill historical filings')
    parser.add_argument('--limit', type=int, help='Limit number of companies (for testing)')
    args = parser.parse_args()
    
    job = BackfillJob(limit=args.limit)
    job.run()


if __name__ == '__main__':
    main()
