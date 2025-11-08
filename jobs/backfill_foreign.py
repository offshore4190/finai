"""
Foreign Company Backfill Job

Backfills foreign filings (20-F, 40-F, 6-K) for identified Foreign Private Issuers.
Supports configurable 6-K inclusion policies to manage volume.

Date window: 2023-01-01 to 2025-12-31 (configurable)
"""
import structlog
from datetime import datetime, date
from typing import Dict, List, Optional

from config.db import get_db_session
from config.settings import settings
from models import Company, Filing, Artifact, ExecutionRun
from services.sec_api import SECAPIClient
from constants import (
    FORM_TYPES_FOREIGN,
    FISCAL_PERIODS_FOREIGN,
    ARTIFACT_TYPE_HTML,
    ARTIFACT_TYPE_IMAGE,
    ARTIFACT_STATUS_PENDING,
    BACKFILL_START_DATE,
    BACKFILL_END_DATE,
)

logger = structlog.get_logger()


def map_fiscal_period(form_type: str, report_date: Optional[date]) -> str:
    """
    Map form type to fiscal period for foreign filings.

    Args:
        form_type: SEC form type (20-F, 40-F, 6-K, etc.)
        report_date: Report date (not used for foreign forms)

    Returns:
        Fiscal period string
    """
    return FISCAL_PERIODS_FOREIGN.get(form_type, 'FY')


def create_filing_record(company_id: int, data: Dict) -> Filing:
    """
    Create a Filing model instance from parsed data.

    Args:
        company_id: Company ID
        data: Parsed filing data

    Returns:
        Filing instance (not yet committed)
    """
    filing = Filing(
        company_id=company_id,
        accession_number=data['accession_number'],
        form_type=data['form_type'],
        filing_date=data['filing_date'],
        report_date=data.get('report_date'),
        fiscal_year=data.get('fiscal_year'),
        fiscal_period=data.get('fiscal_period'),
        primary_document=data.get('primary_document'),
        is_amendment=data.get('is_amendment', False),
        amends_accession=data.get('amends_accession'),
        discovered_at=datetime.utcnow()
    )
    return filing


def create_artifact_records(
    filing_id: int,
    accession: str,
    primary_document: str,
    include_exhibits: bool = False
) -> List[Dict]:
    """
    Create artifact records for a filing.

    Args:
        filing_id: Filing ID
        accession: SEC accession number
        primary_document: Primary document filename
        include_exhibits: Whether to include exhibits

    Returns:
        List of artifact data dicts
    """
    artifacts = []

    # Primary HTML document
    cik_str = accession.split('-')[0]
    accession_clean = accession.replace('-', '')

    primary_url = f"https://www.sec.gov/Archives/edgar/data/{cik_str}/{accession_clean}/{primary_document}"

    artifacts.append({
        'filing_id': filing_id,
        'artifact_type': ARTIFACT_TYPE_HTML,
        'filename': primary_document,
        'url': primary_url,
        'status': ARTIFACT_STATUS_PENDING,
    })

    # TODO: Add exhibit enumeration if include_exhibits=True
    # This would require fetching the filing's index and parsing exhibits

    return artifacts


def should_include_6k_filing(
    form_type: str,
    has_financials: bool,
    include_policy: str = "minimal"
) -> Dict:
    """
    Determine if a 6-K filing should be included based on policy.

    Args:
        form_type: Form type
        has_financials: Whether filing has financial exhibits
        include_policy: "minimal", "financial", or "all"

    Returns:
        Dict with 'include' and 'include_exhibits' flags
    """
    if form_type not in ['6-K', '6-K/A']:
        return {'include': True, 'include_exhibits': True}

    if include_policy == "minimal":
        # Only primary document, no exhibits
        return {'include': True, 'include_exhibits': False}

    elif include_policy == "financial":
        # Include only if has financial exhibits
        return {
            'include': has_financials,
            'include_exhibits': has_financials
        }

    elif include_policy == "all":
        # Include all 6-K filings with exhibits
        return {'include': True, 'include_exhibits': True}

    # Default: minimal
    return {'include': True, 'include_exhibits': False}


def is_filing_duplicate(session, accession_number: str) -> bool:
    """
    Check if a filing already exists in the database.

    Args:
        session: Database session
        accession_number: SEC accession number

    Returns:
        True if filing exists, False otherwise
    """
    existing = session.query(Filing).filter(
        Filing.accession_number == accession_number
    ).first()

    return existing is not None


def create_artifact_if_not_exists(
    session,
    filing_id: int,
    filename: str,
    url: str,
    artifact_type: str
) -> Optional[Artifact]:
    """
    Create an artifact if it doesn't already exist.

    Args:
        session: Database session
        filing_id: Filing ID
        filename: Filename
        url: URL
        artifact_type: Artifact type

    Returns:
        Artifact instance if created, None if already exists
    """
    # Check for duplicate by (filing_id, filename)
    existing = session.query(Artifact).filter(
        Artifact.filing_id == filing_id,
        Artifact.filename == filename
    ).first()

    if existing:
        return None

    artifact = Artifact(
        filing_id=filing_id,
        artifact_type=artifact_type,
        filename=filename,
        url=url,
        status=ARTIFACT_STATUS_PENDING
    )

    return artifact


class ForeignBackfillJob:
    """
    Job to backfill foreign filings for identified FPIs.

    Processes companies marked as is_foreign=True and creates Filing and Artifact
    records for their 20-F, 40-F, and 6-K filings within the date window.
    """

    def __init__(
        self,
        limit: Optional[int] = None,
        exchange: Optional[str] = None,
        include_6k: str = "minimal",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        dry_run: bool = False
    ):
        """
        Initialize the backfill job.

        Args:
            limit: Maximum number of companies to process
            exchange: Filter by exchange (NASDAQ, NYSE, etc.)
            include_6k: 6-K inclusion policy ("minimal", "financial", "all")
            start_date: Start datetime for filing window
            end_date: End datetime for filing window
            dry_run: If True, don't save changes
        """
        self.limit = limit
        self.exchange = exchange
        self.include_6k = include_6k
        self.start_date = start_date or datetime.strptime(BACKFILL_START_DATE, '%Y-%m-%d')
        self.end_date = end_date or datetime.strptime(BACKFILL_END_DATE, '%Y-%m-%d')
        self.dry_run = dry_run
        self.sec_client = SECAPIClient()

        logger.info(
            "foreign_backfill_job_initialized",
            limit=limit,
            exchange=exchange,
            include_6k=include_6k,
            start_date=str(self.start_date),
            end_date=str(self.end_date),
            dry_run=dry_run
        )

    def run(self):
        """Execute the foreign backfill job."""
        logger.info("foreign_backfill_job_started")

        with get_db_session() as session:
            # Create execution run record
            run = ExecutionRun(
                run_type='foreign_backfill',
                started_at=datetime.utcnow(),
                status='running',
                metadata={
                    'limit': self.limit,
                    'exchange': self.exchange,
                    'include_6k': self.include_6k,
                    'start_date': str(self.start_date),
                    'end_date': str(self.end_date),
                    'dry_run': self.dry_run
                }
            )
            session.add(run)
            session.commit()

            try:
                stats = self._process_companies(session, run)

                # Update execution run
                run.completed_at = datetime.utcnow()
                run.status = 'completed'
                run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
                run.filings_discovered = stats['filings_created']
                run.artifacts_attempted = stats['artifacts_created']
                run.metadata.update(stats)

                if not self.dry_run:
                    session.commit()

                logger.info(
                    "foreign_backfill_job_completed",
                    **stats,
                    duration_seconds=run.duration_seconds
                )

            except Exception as e:
                run.status = 'failed'
                run.error_summary = str(e)
                session.commit()

                logger.error(
                    "foreign_backfill_job_failed",
                    error=str(e),
                    exc_info=True
                )
                raise

    def _process_companies(self, session, run: ExecutionRun) -> Dict:
        """
        Process foreign companies to backfill their filings.

        Args:
            session: Database session
            run: Execution run record

        Returns:
            Statistics dictionary
        """
        # Query foreign companies
        query = session.query(Company).filter(
            Company.is_active == True,
            Company.is_foreign == True
        )

        if self.exchange:
            query = query.filter(Company.exchange == self.exchange)

        if self.limit:
            query = query.limit(self.limit)

        companies = query.all()

        stats = {
            'companies_processed': 0,
            'filings_created': 0,
            'filings_skipped_duplicate': 0,
            'filings_skipped_6k': 0,
            'artifacts_created': 0,
            'errors': 0,
            'form_counts': {
                '20-F': 0,
                '40-F': 0,
                '6-K': 0,
            }
        }

        for i, company in enumerate(companies, 1):
            try:
                stats['companies_processed'] += 1

                logger.info(
                    "processing_foreign_company",
                    cik=company.cik,
                    ticker=company.ticker,
                    category=company.fpi_category,
                    progress=f"{i}/{len(companies)}"
                )

                # Fetch submissions
                submissions = self.sec_client.fetch_company_submissions(company.cik)

                # Parse foreign filings
                filings = self.sec_client.parse_filings(
                    submissions,
                    form_types=FORM_TYPES_FOREIGN,
                    start_date=self.start_date,
                    end_date=self.end_date
                )

                # Create Filing and Artifact records
                for filing_data in filings:
                    # Check for duplicates
                    if is_filing_duplicate(session, filing_data['accession_number']):
                        stats['filings_skipped_duplicate'] += 1
                        continue

                    # Apply 6-K policy
                    if filing_data['form_type'] in ['6-K', '6-K/A']:
                        policy = should_include_6k_filing(
                            filing_data['form_type'],
                            has_financials=False,  # TODO: detect from filing
                            include_policy=self.include_6k
                        )

                        if not policy['include']:
                            stats['filings_skipped_6k'] += 1
                            continue

                    # Map fiscal period
                    filing_data['fiscal_period'] = map_fiscal_period(
                        filing_data['form_type'],
                        filing_data.get('report_date')
                    )

                    # Extract fiscal year from report date or filing date
                    report_date = filing_data.get('report_date') or filing_data['filing_date']
                    filing_data['fiscal_year'] = report_date.year

                    # Create Filing
                    filing = create_filing_record(company.id, filing_data)
                    session.add(filing)
                    session.flush()  # Get filing.id

                    stats['filings_created'] += 1

                    # Track form counts
                    base_form = filing_data['form_type'].replace('/A', '')
                    if base_form in stats['form_counts']:
                        stats['form_counts'][base_form] += 1

                    # Create Artifacts
                    artifact_data_list = create_artifact_records(
                        filing_id=filing.id,
                        accession=filing_data['accession_number'],
                        primary_document=filing_data['primary_document'],
                        include_exhibits=False  # TODO: use 6-K policy
                    )

                    for artifact_data in artifact_data_list:
                        artifact = create_artifact_if_not_exists(
                            session,
                            **artifact_data
                        )
                        if artifact:
                            session.add(artifact)
                            stats['artifacts_created'] += 1

                # Commit every 10 companies
                if i % 10 == 0 and not self.dry_run:
                    session.commit()
                    logger.info("progress_checkpoint", processed=i, total=len(companies))

            except Exception as e:
                stats['errors'] += 1
                logger.error(
                    "error_processing_foreign_company",
                    cik=company.cik,
                    ticker=company.ticker,
                    error=str(e)
                )
                # Continue with next company

        # Final commit
        if not self.dry_run:
            session.commit()

        return stats
