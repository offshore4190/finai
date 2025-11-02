"""
Listings Build Job
Fetches NASDAQ and NYSE company listings and populates the companies table.
"""
from datetime import datetime

import structlog

from config.db import get_db_session
from models import Company, ExecutionRun
from services.sec_api import SECAPIClient

logger = structlog.get_logger()


class ListingsBuildJob:
    """Job to build and update company listings."""
    
    def __init__(self):
        """Initialize job."""
        self.sec_client = SECAPIClient()
    
    def run(self):
        """Execute listings build job."""
        logger.info("listings_build_started")
        
        with get_db_session() as session:
            # Create execution run
            run = ExecutionRun(
                run_type='listings_build',
                started_at=datetime.utcnow(),
                status='running'
            )
            session.add(run)
            session.commit()
            
            try:
                # Fetch company tickers from SEC
                tickers_data = self.sec_client.fetch_company_tickers()
                
                companies_added = 0
                companies_updated = 0
                
                # Process each company
                for key, company_data in tickers_data.items():
                    cik = str(company_data['cik_str']).zfill(10)
                    ticker = company_data['ticker'].upper()
                    company_name = company_data['title']

                    # Determine exchange (this is simplified - in reality would need API or data source)
                    # For now, we'll set to 'UNKNOWN' and update later
                    exchange = 'UNKNOWN'

                    # Check if company exists by ticker+exchange (unique key)
                    # Note: Same CIK can have multiple tickers (different share classes, ADRs, etc.)
                    existing = session.query(Company).filter(
                        Company.ticker == ticker,
                        Company.exchange == exchange
                    ).first()

                    if existing:
                        # Update existing
                        existing.cik = cik  # Update CIK in case it changed
                        existing.company_name = company_name
                        existing.is_active = True
                        existing.updated_at = datetime.utcnow()
                        companies_updated += 1
                    else:
                        # Create new
                        company = Company(
                            ticker=ticker,
                            cik=cik,
                            company_name=company_name,
                            exchange=exchange,
                            is_active=True
                        )
                        session.add(company)
                        companies_added += 1
                    
                    # Commit in batches
                    if (companies_added + companies_updated) % 100 == 0:
                        session.commit()
                        logger.info(
                            "listings_progress",
                            added=companies_added,
                            updated=companies_updated
                        )
                
                session.commit()
                
                # Update execution run
                run.completed_at = datetime.utcnow()
                run.status = 'completed'
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
                run.meta_data = {
                    'companies_added': companies_added,
                    'companies_updated': companies_updated,
                    'total_companies': companies_added + companies_updated
                }
                session.commit()
                
                logger.info(
                    "listings_build_completed",
                    added=companies_added,
                    updated=companies_updated,
                    duration_seconds=run.duration_seconds
                )
                
            except Exception as e:
                run.status = 'failed'
                run.error_summary = str(e)
                run.completed_at = datetime.utcnow()
                session.commit()
                
                logger.error("listings_build_failed", error=str(e))
                raise


def main():
    """Main entry point."""
    job = ListingsBuildJob()
    job.run()


if __name__ == '__main__':
    main()
