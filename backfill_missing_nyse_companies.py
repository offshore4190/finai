#!/usr/bin/env python3
"""
Backfill Missing NYSE Companies
Targets active NYSE companies that have no filings yet
"""

import asyncio
from datetime import datetime
from config.db import engine, get_db_session
from models import Company
from jobs.backfill import run_company_backfill
import structlog

logger = structlog.get_logger()


def get_companies_without_filings():
    """Get list of active NYSE companies that have no filings."""
    conn = engine.raw_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT c.id, c.ticker, c.cik, c.company_name, c.exchange
        FROM companies c
        LEFT JOIN filings f ON c.id = f.company_id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        AND c.is_active = true
        AND f.id IS NULL
        ORDER BY c.ticker
    """)

    companies = []
    for row in cur.fetchall():
        companies.append({
            'id': row[0],
            'ticker': row[1],
            'cik': row[2],
            'company_name': row[3],
            'exchange': row[4]
        })

    cur.close()
    conn.close()

    return companies


async def backfill_company(company_info):
    """Backfill a single company."""
    try:
        logger.info(
            "backfilling_company",
            ticker=company_info['ticker'],
            cik=company_info['cik'],
            exchange=company_info['exchange']
        )

        with get_db_session() as session:
            company = session.query(Company).filter_by(id=company_info['id']).first()
            if company:
                # Use the existing backfill job
                from jobs.backfill import discover_and_store_filings

                filings_count = await discover_and_store_filings(
                    session=session,
                    company=company,
                    form_types=['10-K', '10-Q'],
                    fiscal_years=[2023, 2024, 2025]
                )

                logger.info(
                    "company_backfill_complete",
                    ticker=company_info['ticker'],
                    filings_discovered=filings_count
                )

                return {
                    'ticker': company_info['ticker'],
                    'success': True,
                    'filings': filings_count
                }
    except Exception as e:
        logger.error(
            "company_backfill_failed",
            ticker=company_info['ticker'],
            error=str(e)
        )
        return {
            'ticker': company_info['ticker'],
            'success': False,
            'error': str(e)
        }


async def backfill_batch(companies, batch_size=10):
    """Backfill companies in batches to avoid overwhelming the system."""

    print(f"\nStarting backfill for {len(companies)} companies...")
    print(f"Processing in batches of {batch_size}\n")

    total_filings = 0
    success_count = 0
    failed_count = 0

    for i in range(0, len(companies), batch_size):
        batch = companies[i:i+batch_size]
        print(f"\nProcessing batch {i//batch_size + 1}/{(len(companies)-1)//batch_size + 1}")
        print(f"Companies {i+1}-{min(i+batch_size, len(companies))} of {len(companies)}")

        # Process batch in parallel
        tasks = [backfill_company(company) for company in batch]
        results = await asyncio.gather(*tasks)

        # Summarize batch results
        for result in results:
            if result['success']:
                success_count += 1
                total_filings += result['filings']
                print(f"  ✓ {result['ticker']}: {result['filings']} filings")
            else:
                failed_count += 1
                print(f"  ✗ {result['ticker']}: {result.get('error', 'Unknown error')}")

        # Small delay between batches
        if i + batch_size < len(companies):
            print("\nWaiting 5 seconds before next batch...")
            await asyncio.sleep(5)

    return {
        'total': len(companies),
        'success': success_count,
        'failed': failed_count,
        'total_filings': total_filings
    }


def main():
    """Main entry point."""
    print("=" * 80)
    print("NYSE COMPANIES BACKFILL - Missing Companies")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Get companies without filings
    print("Identifying companies without filings...")
    companies = get_companies_without_filings()

    print(f"\nFound {len(companies)} active NYSE companies without filings")

    if not companies:
        print("\n✓ All active NYSE companies already have filings!")
        return

    # Show first 20 companies
    print("\nFirst 20 companies to backfill:")
    for i, company in enumerate(companies[:20], 1):
        print(f"  {i:2}. {company['ticker']:6} - {company['company_name'][:50]:50} ({company['exchange']})")

    if len(companies) > 20:
        print(f"  ... and {len(companies) - 20} more")

    # Ask for confirmation
    print(f"\n⚠️  This will backfill filings for {len(companies)} companies.")
    print("This may take a while depending on the number of filings discovered.")
    response = input("\nProceed with backfill? (y/N): ")

    if response.lower() != 'y':
        print("\nBackfill cancelled.")
        return

    # Run backfill
    print("\nStarting backfill process...")
    results = asyncio.run(backfill_batch(companies, batch_size=10))

    # Final summary
    print("\n" + "=" * 80)
    print("BACKFILL SUMMARY")
    print("=" * 80)
    print(f"Total Companies: {results['total']}")
    print(f"Successful: {results['success']}")
    print(f"Failed: {results['failed']}")
    print(f"Total Filings Discovered: {results['total_filings']:,}")
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


if __name__ == '__main__':
    main()
