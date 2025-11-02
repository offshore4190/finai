"""
Exchange Enrichment Job
Updates company exchange information using listings reference data.
"""
from datetime import datetime
from typing import Dict

import structlog
from sqlalchemy import and_, func

from config.db import get_db_session
from models import Company, ListingsRef, ExecutionRun

logger = structlog.get_logger()


class ExchangeEnrichmentJob:
    """Job to enrich company exchange information from listings reference."""

    def __init__(self):
        """Initialize job."""
        pass

    def run(self):
        """Execute exchange enrichment job."""
        logger.info("exchange_enrichment_started")

        with get_db_session() as session:
            # Create execution run
            run = ExecutionRun(
                run_type='exchange_enrichment',
                started_at=datetime.utcnow(),
                status='running'
            )
            session.add(run)
            session.commit()

            try:
                # Get statistics before enrichment
                total_companies = session.query(func.count(Company.id)).scalar()
                unknown_count_before = session.query(func.count(Company.id)).filter(
                    Company.exchange == 'UNKNOWN'
                ).scalar()

                logger.info(
                    "enrichment_initial_stats",
                    total_companies=total_companies,
                    unknown_exchanges=unknown_count_before
                )

                # Enrich exchanges
                stats = self._enrich_exchanges(session)

                # Get statistics after enrichment
                unknown_count_after = session.query(func.count(Company.id)).filter(
                    Company.exchange == 'UNKNOWN'
                ).scalar()

                # Count by exchange
                exchange_distribution = {}
                exchange_counts = session.query(
                    Company.exchange,
                    func.count(Company.id)
                ).group_by(Company.exchange).all()

                for exchange, count in exchange_counts:
                    exchange_distribution[exchange] = count

                logger.info(
                    "exchange_distribution",
                    distribution=exchange_distribution
                )

                # Update execution run
                run.completed_at = datetime.utcnow()
                run.status = 'completed'
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
                run.meta_data = {
                    'total_companies': total_companies,
                    'unknown_before': unknown_count_before,
                    'unknown_after': unknown_count_after,
                    'enriched': stats['enriched'],
                    'conflicts_resolved': stats['conflicts'],
                    'exchange_distribution': exchange_distribution
                }
                session.commit()

                logger.info(
                    "exchange_enrichment_completed",
                    enriched=stats['enriched'],
                    conflicts=stats['conflicts'],
                    unknown_before=unknown_count_before,
                    unknown_after=unknown_count_after,
                    duration_seconds=run.duration_seconds
                )

            except Exception as e:
                run.status = 'failed'
                run.error_summary = str(e)
                run.completed_at = datetime.utcnow()
                session.commit()

                logger.error("exchange_enrichment_failed", error=str(e), exc_info=True)
                raise

    def _enrich_exchanges(self, session) -> Dict:
        """
        Enrich company exchanges by joining with listings_ref.

        Strategy:
        1. For each company with UNKNOWN exchange
        2. Look up ticker in listings_ref
        3. If multiple matches, prefer non-ETF
        4. Update company.exchange with mapped value

        Args:
            session: Database session

        Returns:
            Dictionary with enrichment statistics
        """
        enriched_count = 0
        conflict_count = 0

        # Get all companies with UNKNOWN exchange
        unknown_companies = session.query(Company).filter(
            Company.exchange == 'UNKNOWN'
        ).all()

        logger.info("processing_unknown_companies", count=len(unknown_companies))

        for company in unknown_companies:
            # Find matching listings (may be multiple if on multiple exchanges)
            matches = session.query(ListingsRef).filter(
                ListingsRef.symbol == company.ticker
            ).all()

            if not matches:
                # No match found
                continue

            # Prefer non-ETF if multiple matches
            selected_match = None

            if len(matches) == 1:
                selected_match = matches[0]
            else:
                # Multiple matches - conflict resolution
                conflict_count += 1

                # Strategy: Prefer non-ETF, then prefer NASDAQ > NYSE > others
                non_etf_matches = [m for m in matches if not m.is_etf]

                if non_etf_matches:
                    # Sort by exchange preference
                    exchange_priority = {'NASDAQ': 0, 'NYSE': 1, 'NYSE American': 2, 'NYSE Arca': 3}
                    sorted_matches = sorted(
                        non_etf_matches,
                        key=lambda m: exchange_priority.get(m.exchange_name, 999)
                    )
                    selected_match = sorted_matches[0]
                else:
                    # All are ETFs, just take first NASDAQ/NYSE
                    exchange_priority = {'NASDAQ': 0, 'NYSE': 1, 'NYSE American': 2, 'NYSE Arca': 3}
                    sorted_matches = sorted(
                        matches,
                        key=lambda m: exchange_priority.get(m.exchange_name, 999)
                    )
                    selected_match = sorted_matches[0]

                logger.debug(
                    "conflict_resolved",
                    ticker=company.ticker,
                    num_matches=len(matches),
                    selected_exchange=selected_match.exchange_name
                )

            # Update company exchange
            if selected_match:
                old_exchange = company.exchange
                company.exchange = selected_match.exchange_name
                company.updated_at = datetime.utcnow()
                enriched_count += 1

                logger.debug(
                    "exchange_updated",
                    ticker=company.ticker,
                    old=old_exchange,
                    new=company.exchange,
                    is_etf=selected_match.is_etf
                )

            # Commit in batches to avoid long transactions
            if enriched_count % 100 == 0:
                session.commit()
                logger.info("enrichment_progress", enriched=enriched_count)

        # Final commit
        session.commit()

        return {
            'enriched': enriched_count,
            'conflicts': conflict_count
        }


def main():
    """Main entry point."""
    job = ExchangeEnrichmentJob()
    job.run()


if __name__ == '__main__':
    main()
