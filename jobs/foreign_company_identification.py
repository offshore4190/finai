"""
Foreign Company Identification Job

Identifies Foreign Private Issuers (FPIs) in the company registry based on multiple signals:
1. Presence of foreign forms (20-F, 40-F) in recent filings
2. Non-US country of incorporation
3. Historical foreign registration forms (F-1, F-3, F-4)

Updates Company records with:
- is_foreign: TRUE for identified FPIs
- fpi_category: 'FPI', 'Canadian FPI', or 'Unknown'
- country_code: ISO 3166-1 alpha-2 country code
"""
import structlog
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from config.db import get_db_session
from config.settings import settings
from models import Company, ExecutionRun
from services.sec_api import SECAPIClient
from constants import (
    FPI_CATEGORY_GENERAL,
    FPI_CATEGORY_CANADIAN,
    FPI_CATEGORY_UNKNOWN,
    FORM_TYPES_FOREIGN,
)

logger = structlog.get_logger()

# US state codes that might appear in stateOrCountry field
US_STATE_CODES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC'
}

# Foreign registration forms
FOREIGN_REGISTRATION_FORMS = ['F-1', 'F-3', 'F-4']


def is_foreign_issuer(submissions: Dict) -> Tuple[bool, List[str]]:
    """
    Determine if a company is a Foreign Private Issuer based on multiple signals.

    Args:
        submissions: SEC submissions data for the company

    Returns:
        Tuple of (is_foreign, signals) where signals is a list of reasons
    """
    signals = []

    # Signal 1: Check for foreign annual report forms (20-F, 40-F)
    if 'filings' in submissions and 'recent' in submissions['filings']:
        recent_forms = submissions['filings']['recent'].get('form', [])

        if '20-F' in recent_forms or '20-F/A' in recent_forms:
            signals.append("20-F form found")

        if '40-F' in recent_forms or '40-F/A' in recent_forms:
            signals.append("40-F form found")

        # Signal 2: Check for foreign registration forms
        for form in FOREIGN_REGISTRATION_FORMS:
            if form in recent_forms:
                signals.append(f"{form} registration form found")

    # Signal 3: Check country of incorporation
    state_or_country = submissions.get('stateOrCountry', '').upper()
    state_of_inc = submissions.get('stateOfIncorporation', '').upper()

    # Determine if the country code is non-US
    # Priority: stateOfIncorporation > stateOrCountry
    if state_of_inc and state_of_inc not in US_STATE_CODES and state_of_inc != 'US':
        signals.append(f"Non-US country of incorporation: {state_of_inc}")
    elif state_or_country and state_or_country not in US_STATE_CODES and state_or_country != 'US':
        signals.append(f"Non-US country: {state_or_country}")

    return len(signals) > 0, signals


def get_country_code(submissions: Dict) -> Optional[str]:
    """
    Extract country code from submissions data.

    Args:
        submissions: SEC submissions data

    Returns:
        ISO 3166-1 alpha-2 country code or None
    """
    # Priority: stateOfIncorporation > stateOrCountry
    state_of_inc = (submissions.get('stateOfIncorporation') or '').upper()
    state_or_country = (submissions.get('stateOrCountry') or '').upper()

    # Check state of incorporation first (more reliable)
    if state_of_inc:
        # If explicitly "US", it's US
        if state_of_inc == 'US':
            return 'US'
        # Special handling for ambiguous codes like CA (California vs Canada)
        # If both fields match and it's potentially a country code, treat as country
        if state_of_inc in US_STATE_CODES:
            # If stateOrCountry matches and is the same, might be country code (e.g., CA = Canada)
            if state_or_country == state_of_inc:
                # CA/CA could be Canada, not California
                # Other state codes are less ambiguous (DE = Delaware for domestic companies)
                # Use the assumption that if both match and no explicit US, could be foreign
                return state_of_inc[:2]
            # If stateOrCountry is explicitly US, then it's a US state
            if state_or_country == 'US':
                return 'US'
            # Otherwise assume US for common state codes
            return 'US'
        # Otherwise treat as foreign country code
        return state_of_inc[:2]

    # Fall back to state or country
    if state_or_country:
        if state_or_country == 'US':
            return 'US'
        # If it's a US state code without incorporation info, assume US
        if state_or_country in US_STATE_CODES:
            # CA/DE could be ambiguous, but without other context, assume US
            return 'US'
        return state_or_country[:2]

    return None


def determine_fpi_category(submissions: Dict) -> str:
    """
    Determine the FPI category based on form types.

    Args:
        submissions: SEC submissions data

    Returns:
        FPI category: 'FPI', 'Canadian FPI', or 'Unknown'
    """
    if 'filings' not in submissions or 'recent' not in submissions['filings']:
        return FPI_CATEGORY_UNKNOWN

    recent_forms = submissions['filings']['recent'].get('form', [])

    # Canadian FPI: uses 40-F
    if '40-F' in recent_forms or '40-F/A' in recent_forms:
        return FPI_CATEGORY_CANADIAN

    # General FPI: uses 20-F
    if '20-F' in recent_forms or '20-F/A' in recent_forms:
        return FPI_CATEGORY_GENERAL

    # Has foreign signals but no clear form type
    return FPI_CATEGORY_UNKNOWN


class ForeignCompanyIdentificationJob:
    """
    Job to identify Foreign Private Issuers in the company registry.

    This job scans companies in the registry and marks those that file
    foreign forms (20-F, 40-F, 6-K) or show other FPI signals.
    """

    def __init__(self, limit: Optional[int] = None, dry_run: bool = False):
        """
        Initialize the identification job.

        Args:
            limit: Maximum number of companies to process (for testing)
            dry_run: If True, don't save changes to database
        """
        self.limit = limit
        self.dry_run = dry_run
        self.sec_client = SECAPIClient()

        logger.info(
            "foreign_identification_job_initialized",
            limit=limit,
            dry_run=dry_run
        )

    def run(self):
        """Execute the foreign company identification job."""
        logger.info("foreign_identification_job_started")

        with get_db_session() as session:
            # Create execution run record
            run = ExecutionRun(
                run_type='foreign_identification',
                started_at=datetime.utcnow(),
                status='running',
                metadata={
                    'limit': self.limit,
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
                run.metadata.update(stats)

                if not self.dry_run:
                    session.commit()

                logger.info(
                    "foreign_identification_job_completed",
                    **stats,
                    duration_seconds=run.duration_seconds
                )

            except Exception as e:
                run.status = 'failed'
                run.error_summary = str(e)
                session.commit()

                logger.error(
                    "foreign_identification_job_failed",
                    error=str(e),
                    exc_info=True
                )
                raise

    def _process_companies(self, session, run: ExecutionRun) -> Dict:
        """
        Process companies to identify foreign issuers.

        Args:
            session: Database session
            run: Execution run record

        Returns:
            Statistics dictionary
        """
        # Query active companies (not already marked as foreign)
        query = session.query(Company).filter(
            Company.is_active == True,
            Company.status == 'active',
            Company.is_foreign == False
        )

        if self.limit:
            query = query.limit(self.limit)

        companies = query.all()

        stats = {
            'companies_scanned': 0,
            'fpis_identified': 0,
            'general_fpis': 0,
            'canadian_fpis': 0,
            'unknown_fpis': 0,
            'errors': 0,
        }

        for i, company in enumerate(companies, 1):
            try:
                stats['companies_scanned'] += 1

                # Fetch submissions from SEC API
                logger.info(
                    "fetching_company_submissions",
                    cik=company.cik,
                    ticker=company.ticker,
                    progress=f"{i}/{len(companies)}"
                )

                submissions = self.sec_client.fetch_company_submissions(company.cik)

                # Check if foreign issuer
                is_fpi, signals = is_foreign_issuer(submissions)

                if is_fpi:
                    stats['fpis_identified'] += 1

                    # Determine category and country
                    category = determine_fpi_category(submissions)
                    country_code = get_country_code(submissions)

                    # Update company record
                    company.is_foreign = True
                    company.fpi_category = category
                    company.country_code = country_code
                    company.updated_at = datetime.utcnow()

                    # Update category stats
                    if category == FPI_CATEGORY_GENERAL:
                        stats['general_fpis'] += 1
                    elif category == FPI_CATEGORY_CANADIAN:
                        stats['canadian_fpis'] += 1
                    else:
                        stats['unknown_fpis'] += 1

                    logger.info(
                        "fpi_identified",
                        cik=company.cik,
                        ticker=company.ticker,
                        category=category,
                        country_code=country_code,
                        signals=signals
                    )

                # Commit every 10 companies
                if i % 10 == 0 and not self.dry_run:
                    session.commit()
                    logger.info("progress_checkpoint", processed=i, total=len(companies))

            except Exception as e:
                stats['errors'] += 1
                logger.error(
                    "error_processing_company",
                    cik=company.cik,
                    ticker=company.ticker,
                    error=str(e)
                )
                # Continue with next company

        # Final commit
        if not self.dry_run:
            session.commit()

        return stats
