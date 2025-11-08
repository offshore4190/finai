"""
Main entry point for the US-Listed Filings ETL system.
Provides CLI interface for running jobs.
"""
import argparse
import sys

import structlog

from config.db import execute_schema_file
from config.settings import settings
from jobs.listings_build import ListingsBuildJob
from jobs.backfill import BackfillJob
from jobs.incremental import IncrementalUpdateJob
from jobs.listings_ref_sync import ListingsRefSyncJob
from jobs.exchange_enrichment import ExchangeEnrichmentJob
from jobs.foreign_company_identification import ForeignCompanyIdentificationJob
from jobs.backfill_foreign import ForeignBackfillJob

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer() if settings.log_format == "json" 
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def init_database():
    """Initialize database schema."""
    logger.info("initializing_database")

    # Execute base schema
    schema_path = "migrations/schema.sql"
    execute_schema_file(schema_path)

    # Execute listings_ref migration
    migration_path = "migrations/002_add_listings_ref.sql"
    execute_schema_file(migration_path)

    # Execute CIK unique constraint removal
    migration_path = "migrations/003_remove_cik_unique_constraint.sql"
    execute_schema_file(migration_path)

    # Execute exchange column size increase
    migration_path = "migrations/004_increase_exchange_column_size.sql"
    execute_schema_file(migration_path)

    # Execute CIK deduplication migration
    migration_path = "migrations/005_deduplicate_cik.sql"
    execute_schema_file(migration_path)

    # Execute SHA256 constraint fix
    migration_path = "migrations/007_fix_sha256_constraint.sql"
    execute_schema_file(migration_path)

    # Execute foreign company support migration
    migration_path = "migrations/008_add_foreign_company_support.sql"
    execute_schema_file(migration_path)

    logger.info("database_initialized")


def run_listings():
    """Run listings build job."""
    logger.info("starting_listings_build")
    job = ListingsBuildJob()
    job.run()


def run_backfill(limit: int = None):
    """Run backfill job."""
    logger.info("starting_backfill", limit=limit)
    job = BackfillJob(limit=limit)
    job.run()


def run_incremental():
    """Run incremental update job."""
    logger.info("starting_incremental_update")
    job = IncrementalUpdateJob()
    job.run()


def run_listings_ref_sync():
    """Run listings reference sync job."""
    logger.info("starting_listings_ref_sync")
    job = ListingsRefSyncJob()
    job.run()


def run_exchange_enrichment():
    """Run exchange enrichment job."""
    logger.info("starting_exchange_enrichment")
    job = ExchangeEnrichmentJob()
    job.run()


def run_foreign_identify(limit: int = None, dry_run: bool = False):
    """Run foreign company identification job."""
    logger.info("starting_foreign_identification", limit=limit, dry_run=dry_run)
    job = ForeignCompanyIdentificationJob(limit=limit, dry_run=dry_run)
    job.run()


def run_foreign_backfill(
    limit: int = None,
    exchange: str = None,
    include_6k: str = "minimal",
    dry_run: bool = False
):
    """Run foreign company backfill job."""
    logger.info(
        "starting_foreign_backfill",
        limit=limit,
        exchange=exchange,
        include_6k=include_6k,
        dry_run=dry_run
    )
    job = ForeignBackfillJob(
        limit=limit,
        exchange=exchange,
        include_6k=include_6k,
        dry_run=dry_run
    )
    job.run()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='US-Listed Filings ETL System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize database
  python main.py init-db

  # Build company listings (all ~13k SEC filers)
  python main.py listings

  # Sync exchange reference data from NASDAQ/NYSE
  python main.py listings-ref-sync

  # Enrich company exchange info (UNKNOWN -> NASDAQ/NYSE)
  python main.py exchange-enrichment

  # Backfill historical filings (all companies)
  python main.py backfill

  # Backfill with limit (for testing)
  python main.py backfill --limit 10

  # Run incremental update (weekly)
  python main.py incremental
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Init DB command
    subparsers.add_parser('init-db', help='Initialize database schema')

    # Listings command
    subparsers.add_parser('listings', help='Build/update company listings (all ~13k SEC filers)')

    # Listings reference sync command
    subparsers.add_parser('listings-ref-sync', help='Sync NASDAQ/NYSE exchange reference data')

    # Exchange enrichment command
    subparsers.add_parser('exchange-enrichment', help='Enrich company exchange info from reference data')

    # Backfill command
    backfill_parser = subparsers.add_parser('backfill', help='Backfill historical filings')
    backfill_parser.add_argument('--limit', type=int, help='Limit number of companies (for testing)')

    # Incremental command
    subparsers.add_parser('incremental', help='Run incremental update (weekly)')

    # Foreign company identification command
    foreign_identify_parser = subparsers.add_parser(
        'foreign-identify',
        help='Identify Foreign Private Issuers (FPIs) in company registry'
    )
    foreign_identify_parser.add_argument('--limit', type=int, help='Limit number of companies (for testing)')
    foreign_identify_parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no changes saved)')

    # Foreign company backfill command
    foreign_backfill_parser = subparsers.add_parser(
        'foreign-backfill',
        help='Backfill foreign filings (20-F/40-F/6-K) for identified FPIs'
    )
    foreign_backfill_parser.add_argument('--limit', type=int, help='Limit number of companies (for testing)')
    foreign_backfill_parser.add_argument(
        '--exchange',
        choices=['NASDAQ', 'NYSE'],
        help='Filter by exchange'
    )
    foreign_backfill_parser.add_argument(
        '--include-6k',
        choices=['minimal', 'financial', 'all'],
        default='minimal',
        help='6-K inclusion policy (default: minimal)'
    )
    foreign_backfill_parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no changes saved)')

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == 'init-db':
            init_database()
        elif args.command == 'listings':
            run_listings()
        elif args.command == 'listings-ref-sync':
            run_listings_ref_sync()
        elif args.command == 'exchange-enrichment':
            run_exchange_enrichment()
        elif args.command == 'backfill':
            run_backfill(limit=args.limit)
        elif args.command == 'incremental':
            run_incremental()
        elif args.command == 'foreign-identify':
            run_foreign_identify(limit=args.limit, dry_run=args.dry_run)
        elif args.command == 'foreign-backfill':
            run_foreign_backfill(
                limit=args.limit,
                exchange=args.exchange,
                include_6k=args.include_6k,
                dry_run=args.dry_run
            )

        logger.info("command_completed", command=args.command)
        
    except Exception as e:
        logger.error("command_failed", command=args.command, error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
